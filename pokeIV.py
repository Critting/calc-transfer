#!/usr/bin/env python
import os
import re
import sys
import json
import time
import struct
import pprint
import logging
import requests
import argparse
import getpass
import csv
import time

sys.path.insert(0, './pogo')
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

# add directory of this file to PATH, so that the package will be found
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def init_config():
    parser = argparse.ArgumentParser()
    config_file = "config.json"

    # If config file exists, load variables from json
    load   = {}
    if os.path.isfile(config_file):
        with open(config_file) as data:
            load.update(json.load(data))
    
    # Read passed in Arguments
    required = lambda x: not x in load
    parser.add_argument("-a", "--auth_service", help="Auth Service ('ptc' or 'google')",required=required("auth_service"))
    parser.add_argument("-u", "--username", help="Username", required=required("username"))
    parser.add_argument("-p", "--password", help="Password")
    parser.add_argument("-l", "--location", help="Location", required=required("location"))
    parser.add_argument("-t", "--transfer", help="Transfers all but the highest of each pokemon (see -m)", action="store_true")
    parser.add_argument("-e", "--evolve", help="Evolves as many T1 pokemon that it can (starting with highest IV)", action="store_true")
    parser.add_argument("-m", "--minimumIV", help="All pokemon equal to or above this IV value are kept regardless of duplicates")
    parser.add_argument("-me", "--max_evolutions", help="Maximum number of evolutions in one pass")
    parser.add_argument("-ed", "--evolution_delay", help="delay between evolutions in seconds")
    parser.add_argument("-td", "--transfer_delay", help="delay between transfers in seconds")
    parser.add_argument("-hm", "--hard_minimum", help="transfer candidates will be selected if they are below minimumIV (will transfer unique pokemon)", action="store_true")
    parser.add_argument("-cp", "--cp_override", help="will keep pokemon that have CP equal to or above the given limit, regardless of IV")
    parser.add_argument("-v", "--verbose", help="displays additional information about each pokemon", action="store_true")
    parser.set_defaults(EVOLVE=False, VERBOSE=False)
    config = parser.parse_args()
	  
    # Passed in arguments shoud trump
    for key in config.__dict__:
        if key in load and config.__dict__[key] is None and load[key]:
            config.__dict__[key] = str(load[key])

    if config.__dict__["password"] is None:
        log.info("Secure Password Input (if there is no password prompt, use --password <pw>):")
        config.__dict__["password"] = getpass.getpass()

    if config.auth_service not in ['ptc', 'google']:
        log.error("Invalid Auth service specified! ('ptc' or 'google')")
        return None
        
    if config.__dict__["minimumIV"] is None:
        config.__dict__["minimumIV"] = "101"
    if config.__dict__["max_evolutions"] is None:
        config.__dict__["max_evolutions"] = "71"
    if config.__dict__["evolution_delay"] is None:
        config.__dict__["evolution_delay"] = "25"
    if config.__dict__["transfer_delay"] is None:
        config.__dict__["transfer_delay"] = "10"

    return config

def get_needed_counts(pokemon, uniques, evolves):
    needed = dict()
    for p in pokemon:
        if str(p.number) in evolves and str(p.number) in uniques:
           needed[str(p.number)] = evolves[str(p.number)] - uniques[str(p.number)]
    return needed

def get_unique_counts(pokemon):
    uniques = dict()
    for p in pokemon:
        if (str(p.number) == str(p.family)):
           if str(p.number) in uniques:
                uniques[str(p.number)] = uniques[str(p.number)] + 1
           else:
                uniques[str(p.number)] = 1
    return uniques
				
def get_evolve_counts(pokemon):
    evolves = dict()
    total = 0
    for p in pokemon:
        if str(p.number) == str(p.family) and str(p.number) not in evolves and hasattr(p,'cost'):
            extraCandy = (p.candy/p.cost)*2 #we get 2 everytime we evolve (evol + transfer)
            totalCandy = p.candy + extraCandy
            while int(extraCandy/p.cost) >= 1:
                totalCandy += 2 #2 more for every evolve we get from extras
                extraCandy = int(extraCandy/p.cost) + 2
            if int(totalCandy/p.cost) > 0:
                evolves[str(p.number)] = int(totalCandy/p.cost)
                total += int(totalCandy/p.cost)
    evolves["total"] = total
    return evolves

def get_pokemon(pokemon, candies):
    data = []
    
    with open('names.tsv') as f:
        f.readline()
        names = dict(csv.reader(f, delimiter='\t'))
        
    with open('families.tsv') as f:
        f.readline()
        families = dict(csv.reader(f, delimiter='\t'))
        
    with open('evolves.tsv') as f:
        f.readline()
        evolves = dict(csv.reader(f, delimiter='\t'))
    
    for p in pokemon:
        pok = type('',(),{})
        pok.id = p.id
        pok.number = p.pokemon_id
        pok.name = names[str(pok.number)]
        pok.family = families[str(pok.number)]
        pok.stamina = int(p.individual_stamina) if hasattr(p,"individual_stamina") else 0
        pok.attack = int(p.individual_attack) if hasattr(p,"individual_attack") else 0
        pok.defense = int(p.individual_defense) if hasattr(p,"individual_defense") else 0
        pok.iv = ((pok.stamina + pok.attack + pok.defense) / float(45))*100
        pok.ivPercent = pok.iv/100
        pok.cp = p.cp
        if int(evolves[str(pok.number)]) > 0:
            pok.cost = int(evolves[str(pok.number)])
        pok.candy = candies[int(pok.family)]
        data.append(pok)
    return data

def get_above_iv(pokemon, ivmin):
    if len(pokemon) == 0:
        return []
    best = []
    
    #sort by iv
    pokemon.sort(key=lambda x: x.iv, reverse=True)
    for p in pokemon:
        #if it passes the minimum iv test
        if p.iv >= float(ivmin):			
            best.append(p)

    return best

def get_best_pokemon(pokemon, ivmin, cpmin):
    if len(pokemon) == 0:
        return []

    best = []
    
    #sort by iv
    pokemon.sort(key=lambda x: x.iv, reverse=True)
    for p in pokemon:
        #if there isn't a pokemon in best with the same number (name) as this one, add it
        if not any(x.number == p.number for x in best):
            best.append(p)
        #if it passes the minimum iv test
        elif p.iv >= float(ivmin):
            best.append(p)
        #if cp_override is set, check CP
        elif cpmin > 0 and int(p.cp) >= int(cpmin):
            best.append(p)

    return best

def main():
    setupLogger()
    logging.debug('Logger set up')

    config = init_config()
    if not config:
        return

    # Create PokoAuthObject
    poko_session = PokeAuthSession(
        config.username,
        config.password,
        config.auth_service,
        geo_key=""
    )
    
    # Authenticate with a given location
    # Location is not inherent in authentication
    # But is important to session
    session = poko_session.authenticate(config.location)
    
    # Time to show off what we can do
    if not session:
        logging.critical('Session not created successfully')
        return
    
    #get inventory
    inventory = session.getInventory()
    pokemon = inventory["party"]
    candy = inventory["candies"]
    
    # add candy to pokemon and reformat the list
    pokemon = get_pokemon(pokemon, candy)
    
    if len(pokemon) == 0:
        print('You have no pokemon...')
        return
    # highest IV pokemon
    best = []
    if config.hard_minimum:
        best = get_above_iv(pokemon, float(config.minimumIV))
    else:
        mincp = int(config.cp_override) if config.cp_override is not None else 0
        best = get_best_pokemon(pokemon, float(config.minimumIV), mincp)
    # rest of pokemon
    extras = list(set(pokemon) - set(best))
    others = []
    transfers = []
    # evolution information
    uniques = get_unique_counts(pokemon)
    evolves = get_evolve_counts(pokemon)
    needed = get_needed_counts(pokemon, uniques, evolves)    
    #------- get transfers and other
    if extras:
        extras.sort(key=lambda x: x.iv)
        used = dict()
        for p in extras:
            id = str(p.number)
            used[id] = 0 if id not in used else used[id]
            if id not in evolves.keys() or used[id] < (uniques[id] - evolves[id]):
                transfers.append(p)
            else:
                others.append(p)
            used[id] = used[id] + 1
    others.sort(key=lambda x: x.iv, reverse=True)
    transfers.sort(key=lambda x: x.iv)	
    #------- best pokemon
    if best:
        print('{0:<15} {1:^20} {2:>15}'.format('------------','Highest IV Pokemon','------------'))
        if config.verbose:
            print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}'.format('[POKEMON]','[ATK]','[DEF]','[STA]','[CP]','[IV]'))
            for p in best:
                print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8.2%}'.format(str(p.name),str(p.attack),str(p.defense),str(p.stamina),str(p.cp),p.ivPercent))
        else:
            print('{0:<10} {1:>8} {2:>8}'.format('[pokemon]','[CP]','[IV]'))
            for p in best:
                print('{0:<10} {1:>8} {2:>8.2%}'.format(str(p.name),str(p.cp),p.ivPercent))
    #------- transferable pokemon
    if transfers:	
        print('{0:<15} {1:^20} {2:>15}'.format('------------','May be transfered','------------'))
        if config.verbose:
            print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}'.format('[POKEMON]','[ATK]','[DEF]','[STA]','[CP]','[IV]'))
            for p in transfers:
                print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8.2%}'.format(str(p.name),str(p.attack),str(p.defense),str(p.stamina),str(p.cp),p.ivPercent))  
        else:
            print('{0:<10} {1:>8} {2:>8}'.format('[pokemon]','[CP]','[IV]'))
            for p in transfers:
                print('{0:<10} {1:>8} {2:>8.2%}'.format(str(p.name),str(p.cp),p.ivPercent))
    #------- extras that aren't to be transfered
    if others:
        print('{0:<15} {1:^20} {2:>15}'.format('------------','Other Pokemon','------------'))
        if config.verbose:
            print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}'.format('[POKEMON]','[ATK]','[DEF]','[STA]','[CP]','[IV]'))
            for p in others:
                print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8.2%}'.format(str(p.name),str(p.attack),str(p.defense),str(p.stamina),str(p.cp),p.ivPercent))
        else:
            print('{0:<10} {1:>8} {2:>8}'.format('[pokemon]','[CP]','[IV]'))
            for p in others:
                print('{0:<10} {1:>8} {2:>8.2%}'.format(str(p.name),str(p.cp),p.ivPercent))
    #------- evolve candidate  pokemon
    if any(evolves):
        print('{0:<15} {1:^20} {2:>15}'.format('------------','Available evolutions','------------'))
        print('{0:<15} {1:^20} {2:>15}'.format('------------','TOTAL: '+str(evolves["total"])+' / '+config.max_evolutions,'------------'))
        print('{0:<10} {1:<15} {2:<17} {3:>10}'.format('[pokemon]','[# evolutions]','[# in inventory]','[# needed]'))
    shown = []
    for p in pokemon:
        id = str(p.number)
        if id not in shown and id in evolves.keys():
            shown.append(id)
            if needed[id] <= 0:
                print('{0:<10} {1:^15} {2:^17} {3:^10}'.format(str(p.name),evolves[id],uniques[id],""))
            else:
                print('{0:<10} {1:^15} {2:^17} {3:^10}'.format(str(p.name),evolves[id],uniques[id],needed[id]))

    #------- transfer extra pokemon
    if config.transfer:
        for p in transfers:
            logging.info('{0:<35} {1:<8} {2:<8.2%}'.format('transferring pokemon: '+str(p.name),str(p.cp),p.ivPercent,))
            session.releasePokemon(p)
            if id in uniques.keys():
                uniques[id] = uniques[id] - 1 #we now have one fewer of these...
            time.sleep(int(config.transfer_delay))

    #------- evolving t1 pokemon
    if config.evolve:
        pokemon.sort(key=lambda x: x.iv, reverse=True)
        evolved = True
        count = 0
        while evolved and count < int(config.max_evolutions):
            evolved = False
            for p in pokemon[:]:
                id = str(p.number)
                if id in evolves.keys() and (evolves[id] - needed[id]) > 0:
                    logging.info('{0:<35} {1:<8} {2:<8.2%}'.format('evolving pokemon: '+str(p.name),str(p.cp),p.ivPercent))
                    session.evolvePokemon(p)
                    evolves[id] = evolves[id] - 1
                    uniques[id] = uniques[id] - 1
                    pokemon.remove(p)
                    evolved = True
                    count += 1
                    time.sleep(int(config.evolution_delay))
    
if __name__ == '__main__':
    main()
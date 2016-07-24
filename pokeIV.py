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

# -- global dictionaries for pokedex, families, and evolution prices
with open('names.tsv') as f:
    f.readline()
    POKEDEX = dict(csv.reader(f, delimiter='\t'))
    
with open('families.tsv') as f:
    f.readline()
    FAMILIES = dict(csv.reader(f, delimiter='\t'))    
    
with open('evolves.tsv') as f:
    f.readline()
    COSTS = dict(csv.reader(f, delimiter='\t'))

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
    parser.add_argument("-el", "--evolve_list", help="list of the only pokemon to evolve by ID (ex: 1 = bulbasaur)", action="append")
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
				
def get_evolve_counts(pokemon, evolve_list):
    evolves = dict()
    total = 0
    
    if evolve_list is not None:
        evolve_list = [x.lower() for x in evolve_list]
    
    for p in pokemon:
        if evolve_list is not None and str(p.number) not in evolve_list and p.name.lower() not in evolve_list:
            continue
        if str(p.number) == str(p.family) and str(p.number) not in evolves and hasattr(p,'cost'):
            if int(p.candy/p.cost) > 0:
                evolves[str(p.number)] = int(p.candy/p.cost)
                total += int(p.candy/p.cost)
    evolves["total"] = total
    return evolves

def get_pokemon(pokemon, candies):
    data = []
    
    for p in pokemon:
        pok = type('',(),{})
        pok.id = p.id
        pok.number = p.pokemon_id
        pok.name = POKEDEX[str(pok.number)]
        pok.family = FAMILIES[str(pok.number)]
        pok.stamina = int(p.individual_stamina) if hasattr(p,"individual_stamina") else 0
        pok.attack = int(p.individual_attack) if hasattr(p,"individual_attack") else 0
        pok.defense = int(p.individual_defense) if hasattr(p,"individual_defense") else 0
        pok.iv = ((pok.stamina + pok.attack + pok.defense) / float(45))*100
        pok.ivPercent = pok.iv/100
        pok.cp = p.cp
        if int(COSTS[str(pok.number)]) > 0:
            pok.cost = int(COSTS[str(pok.number)])
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

def print_header(title):
    print('{0:<15} {1:^20} {2:>15}'.format('------------',title,'------------'))

def print_pokemon(pokemon, verbose):
    if verbose:
        print_pokemon_verbose(pokemon)
    else:
        print_pokemon_min(pokemon)
    
def print_pokemon_min(pokemon):
    print('{0:<10} {1:>8} {2:>8}'.format('[pokemon]','[CP]','[IV]'))
    for p in pokemon:
        print('{0:<10} {1:>8} {2:>8.2%}'.format(str(p.name),str(p.cp),p.ivPercent)) 

def print_pokemon_verbose(pokemon):
    print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}'.format('[POKEMON]','[ATK]','[DEF]','[STA]','[CP]','[IV]'))
    for p in pokemon:
        print('{0:<10} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8.2%}'.format(str(p.name),str(p.attack),str(p.defense),str(p.stamina),str(p.cp),p.ivPercent))

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
    evolutions = []
    # evolution information
    uniques = get_unique_counts(pokemon)
    evolves = get_evolve_counts(pokemon, config.evolve_list)
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
    #------- get pokemon to be evolved
    if any(evolves):
        pokemon.sort(key=lambda x: x.iv, reverse=True)
        count = dict()
        for p in pokemon:
            id = str(p.number)
            count[id] = 0 if id not in count else count[id]
            if id in evolves.keys() and count[id] < int(evolves[id]):
                evolutions.append(p)
                count[id] = count[id] + 1
    #------- best pokemon
    if best:
        print_header('Highest IV Pokemon')
        print_pokemon(best, config.verbose)
    #------- transferable pokemon
    if transfers:
        print_header('May be transfered')
        print_pokemon(transfers, config.verbose)
    #------- extras that aren't to be transfered
    if others:
        print_header('Other Pokemon')
        print_pokemon(others, config.verbose)
    #------- evolve candidate  pokemon
    if evolutions:
        print_header('Available evolutions')
        print_header('TOTAL: '+str(evolves["total"])+' / '+config.max_evolutions)
        print('{0:<10} {1:<15} {2:<17} {3:>10}'.format('[pokemon]','[# evolutions]','[# in inventory]','[# needed]'))
        for id in list(evolves.keys()):
            if id in needed.keys() and id in uniques.keys() and needed[id] <= 0:
                print('{0:<10} {1:^15} {2:^17} {3:^10}'.format(POKEDEX[id],evolves[id],uniques[id],""))
            elif id in needed.keys() and id in uniques.keys():
                print('{0:<10} {1:^15} {2:^17} {3:^10}'.format(POKEDEX[id],evolves[id],uniques[id],needed[id]))
    #------- transfer extra pokemon
    if config.transfer and transfers:
        print('{0:<15} {1:^20} {2:>15}'.format('------------','Transferring','------------'))
        for p in transfers[:]:
            logging.info('{0:<35} {1:<8} {2:<8.2%}'.format('transferring pokemon: '+str(p.name),str(p.cp),p.ivPercent,))
            session.releasePokemon(p)
            if id in uniques.keys():
                uniques[id] = uniques[id] - 1 #we now have one fewer of these...
            if p in transfers:
                transfers.remove(p)
            if p in pokemon:
                pokemon.remove(p)
            time.sleep(int(config.transfer_delay))
    #------- evolving t1 pokemon
    if config.evolve and evolutions:
        for p in evolutions[:]:
            logging.info('{0:<35} {1:<8} {2:<8.2%}'.format('evolving pokemon: '+str(p.name),str(p.cp),p.ivPercent))
            session.evolvePokemon(p)
            evolves[id] = evolves[id] - 1
            uniques[id] = uniques[id] - 1
            if p in evolutions:
                evolutions.remove(p)
            if p in pokemon:
                pokemon.remove(p)
            if p in extras:
                extras.remove(p)
            time.sleep(int(config.evolution_delay))
    
if __name__ == '__main__':
    main()
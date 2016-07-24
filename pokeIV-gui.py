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
import tkinter as tk
from collections import OrderedDict

from pokemondata import PokemonData
from pokeivwindow import PokeIVWindow

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
    parser.add_argument("-m", "--minimumIV", help="All pokemon equal to or above this IV value are kept regardless of duplicates")
    parser.add_argument("-me", "--max_evolutions", help="Maximum number of evolutions in one pass")
    parser.add_argument("-ed", "--evolution_delay", help="delay between evolutions in seconds")
    parser.add_argument("-td", "--transfer_delay", help="delay between transfers in seconds")
    parser.add_argument("-hm", "--hard_minimum", help="transfer candidates will be selected if they are below minimumIV (will transfer unique pokemon)", action="store_true")
    parser.add_argument("-cp", "--cp_override", help="will keep pokemon that have CP equal to or above the given limit, regardless of IV")
    parser.add_argument("-v", "--verbose", help="displays additional information about each pokemon", action="store_true")
    parser.add_argument("-el", "--evolve_list", help="Evolve lsit has been deprecated. Please use white list instead (-wl).", action="append")
    parser.add_argument("-wl", "--white_list", help="list of the only pokemon to transfer and evolve by ID or name (ex: -wl 1 = -wl bulbasaur)", action="append")
    parser.add_argument("-bl", "--black_list", help="list of the pokemon not to transfer and evolve by ID or name (ex: -bl 1 = -bl bulbasaur)", action="append")
    parser.add_argument("-f", "--force", help="forces all pokemon not passing the IV threshold to be transfer candidates regardless of evolution", action="store_true")
    config = parser.parse_args()
    
    # Passed in arguments shoud trump
    for key in config.__dict__:
        if key in load and config.__dict__[key] is None and load[key]:
            if key == "black_list" or key == "white_list":
                config.__dict__[key] = str(load[key]).split(',')
            else:
                config.__dict__[key] = str(load[key])
        elif key in load and (type(config.__dict__[key]) == type(True)) and not config.__dict__[key] and load[key]: #if it's boolean and false
            if str(load[key]) == "True":
                config.__dict__[key] = True
    
    if config.__dict__["password"] is None:
        logging.info("Secure Password Input (if there is no password prompt, use --password <pw>):")
        config.__dict__["password"] = getpass.getpass()

    if config.auth_service not in ['ptc', 'google']:
        logging.error("Invalid Auth service specified! ('ptc' or 'google')")
        return None
        
    if config.__dict__["minimumIV"] is None:
        config.__dict__["minimumIV"] = "101"
    if config.__dict__["max_evolutions"] is None:
        config.__dict__["max_evolutions"] = "71"
    if config.__dict__["evolution_delay"] is None:
        config.__dict__["evolution_delay"] = "25"
    if config.__dict__["transfer_delay"] is None:
        config.__dict__["transfer_delay"] = "10"
    
    if config.white_list is not None and config.black_list is not None:
        logging.error("Black list and white list can not be used together.")
        return
    
    if config.evolve_list is not None:
        logging.error("Evolve lsit has been deprecated. Please use white list instead (-wl).")
        return
    
    if config.white_list is not None:
        config.white_list = [x.lower() for x in config.white_list]
    if config.black_list is not None:
        config.black_list = [x.lower() for x in config.black_list]
    
    return OrderedDict(sorted(vars(config).items())) #namespaces are annoying => sorted dict

def main():
    setupLogger()
    logging.debug('Logger set up')

    config = init_config()
    if not config:
        return

    # Create PokoAuthObject
    poko_session = PokeAuthSession(
        config["username"],
        config["password"],
        config["auth_service"],
        geo_key=""
    )
    
    # Authenticate with a given location
    # Location is not inherent in authentication
    # But is important to session
    session = poko_session.authenticate(config["location"])
    
    # Time to show off what we can do
    if not session:
        logging.critical('Session not created successfully')
        return
    
    #get inventory
    inventory = session.getInventory()
    pokemon = inventory["party"]
    candy = inventory["candies"]
    
    # -- dictionaries for pokedex, families, and evolution prices
    with open('names.tsv') as f:
        f.readline()
        pokedex = dict(csv.reader(f, delimiter='\t'))
        
    with open('families.tsv') as f:
        f.readline()
        family = dict(csv.reader(f, delimiter='\t'))    
        
    with open('evolves.tsv') as f:
        f.readline()
        cost = dict(csv.reader(f, delimiter='\t'))
    
    data = PokemonData(pokemon, candy, pokedex, family, cost, config, session)
       
    main_window = tk.Tk()
    app = PokeIVWindow(config,data,session,master=main_window)
    app.mainloop()
    
if __name__ == '__main__':
    main()
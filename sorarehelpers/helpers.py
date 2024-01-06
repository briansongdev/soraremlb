import requests
import json
import os
import pandas as pd

from unidecode import unidecode

URL = "https://api.sorare.com/federation/graphql"
APIKEY = "834eaada2776d187c02c7ac077a3a13bb019cc47f883c67335b5dece3ec3327a5d6cd8b2ce7369b9da511b5648a6e915c950857a6231088b121b1690824sr128"

def check_cache(filename):
    if os.path.isfile(filename):
        return json.load(open(filename))

def get_players(QUERY, quiet):
    js_obj = json.loads(requests.post(URL, headers={"APIKEY": APIKEY}, json={'query': QUERY}).text)
    if 'error' in js_obj:
        return [], ""
    list_of_players, next_cursor = [player['node']['slug'] for player in js_obj['data']['tokens']['allNfts']['edges']], js_obj['data']['tokens']['allNfts']['pageInfo']['endCursor']
    if not quiet: print(list_of_players)
    return list_of_players, next_cursor

def get_query_with_start_cursor(quiet, STARTCURSOR=""):
    if STARTCURSOR == "":
        QUERY = """{
            tokens {
                allNfts(sport: [BASEBALL], rarities: [super_rare]) {
                edges {
                    node {
                    slug
                    }
                }
                pageInfo {
                    hasNextPage
                    startCursor
                    endCursor
                }
                }
            }
        }"""
        return get_players(QUERY, quiet=quiet)
    QUERY = """{
        tokens {
            allNfts(sport: [BASEBALL], rarities: [super_rare], after:"%s") {
            edges {
                node {
                slug
                }
            }
            pageInfo {
                hasNextPage
                startCursor
                endCursor
            }
            }
        }
    }""" % (STARTCURSOR)
    return get_players(QUERY, quiet=quiet)

def process_player_slugs(slug):
    return ['-'.join(player.split('-')[:-3]) for player in slug]

def populate_players(save=True, quiet=False):
    '''
    One-run function. Iterates through cards of high rarity to minimize duplicates, and adds those to a player register for post-processing in the bot.

    save: Saves output to a separate file on the disk.
    quiet: Suppresses output from API calls
    '''

    cache = check_cache("./players-slug.json")
    if cache: return cache

    players = []
    print("In progress, please wait...")
    listOfPlayers = get_query_with_start_cursor(quiet=quiet)
    while listOfPlayers[1]:
        players.extend(process_player_slugs(listOfPlayers[0]))
        listOfPlayers = get_query_with_start_cursor(listOfPlayers[1], quiet=quiet)
    players = list(set(players))
    
    filtered_player_arr = json.dumps(players, indent=4)
    if save:
        with open("players-slug.json", "w") as out:
            out.write(filtered_player_arr)

def filter_names_that_are_present_in_2023(sorarejson):
    print("Filtering names that have only played in 2023...")
    to_keep = json.load(open(sorarejson))
    sorare_arr = [unidecode(slug + "-2023-limited-1") for slug in json.load(open(sorarejson))]
    start, result = 0, []
    while start < len(sorare_arr):
        SLUG_QUERY = """{
            baseballCards(slugs: %s) {
                player {
                    displayName
                }
            }
        }""" % (json.dumps(sorare_arr[start:start + 50]))
        js_obj = json.loads(requests.post(URL, headers={"APIKEY": APIKEY}, json={'query': SLUG_QUERY}).text)
        result.extend([unidecode(_["player"]["displayName"]).lower() for _ in js_obj["data"]["baseballCards"]])
        start += 50
    first_ctr, second_ctr = 0, 0
    final_res = []
    while first_ctr < len(sorare_arr) and second_ctr < len(result):
        if result[second_ctr].split(" ")[-1] in sorare_arr[first_ctr] or result[second_ctr].split(" ")[-2] in sorare_arr[first_ctr]:
            final_res.append(first_ctr)
            second_ctr += 1
        first_ctr += 1
    return [to_keep[id] for id in final_res]

def generate_names(save=True, sorarejson=""):
    '''
    Generates name objects from the slug of a player's Sorare ID.

    save: Saves output to a separate file on the disk.
    sorarejson: JSON file with Sorare slug data
    '''
    cache = check_cache("./players-names-slug.json")
    if cache: return cache

    sorare_arr = filter_names_that_are_present_in_2023(sorarejson)
    sorare_arr_with_limited_rarity = [slug + "-2023-limited-1" for slug in sorare_arr]
    print("In progress, please wait...")

    start, player_arr = 0, []
    while start < len(sorare_arr):
        SLUG_QUERY = """{
            baseballPlayers(slugs: %s) {
                firstName
                lastName
                positions
            }
            baseballCards(slugs: %s) {
                player {
                    displayName
                }
            }
        }""" % (json.dumps(sorare_arr[start:start + 50]), json.dumps(sorare_arr_with_limited_rarity[start:start + 50]))
        js_obj = json.loads(requests.post(URL, headers={"APIKEY": APIKEY}, json={'query': SLUG_QUERY}).text)

        first_result, second_result = js_obj["data"]["baseballPlayers"], [unidecode(_["player"]["displayName"].lower()) for _ in js_obj["data"]["baseballCards"]]
        for obj in first_result: obj["firstName"], obj["lastName"] = unidecode(obj["firstName"].lower()), unidecode(obj["lastName"].lower())
        player_arr.extend(zip(first_result, second_result))
        print("Players", start, "to", start + 50, "added.")
        start += 50
    print("Length of player-name-matched array (active players):", len(player_arr))

    dumped_player_arr = json.dumps(player_arr, indent=4)
    if save:
        with open("players-names-slug.json", "w") as out:
            out.write(dumped_player_arr)
    print("Done! File is at players-name-slug.json." if save else "Done!")
    
    return player_arr


def compare_names(save=True, mlbjson="", sorarejson=""):
    '''
    Attempts to match names from Sorare Player Cards to those in the official baseball registry.

    save: Saves output to a separate file on the disk.
    ...json: Respective JSON files for data
    '''
    mlb_registry_arr = json.load(open(mlbjson))
    sorare_arr = generate_names(sorarejson=sorarejson)
    # print(mlb_registry_arr)
    # for player in sorare_arr:

    
compare_names(mlbjson="../sorarebot/playerslastdecade.json", sorarejson="./players-slug.json")

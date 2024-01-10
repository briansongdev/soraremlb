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
        player_arr.extend(zip(first_result, second_result, sorare_arr[start:start + 50]))
        print("Players", start, "to", start + 50, "added.")
        start += 50
    print("Length of player-name-matched array (active players):", len(player_arr))

    dumped_player_arr = json.dumps(player_arr, indent=4)
    if save:
        with open("players-names-slug.json", "w") as out:
            out.write(dumped_player_arr)
    print("Done! File is at players-name-slug.json." if save else "Done!")
    
    return player_arr

def contains_some_match(playName, fullPlayer):
    '''
    Attempts to determine if some match (fuzzy) exists between the player's full name and the name the player uses for lineups/etc.

    playName: name given by MLB registry: "kris bryant"
    fullPlayer: player list retrieved from post-processing (Sorare side). For example:
        [
            {
                "firstName": "kristopher",
                "lastName": "bryant",
                "positions": [
                    "OUTFIELD",
                    "DESIGNATED_HITTER"
                ]
            },
            "kris bryant",
            "kris-bryant-19920104"
        ]
    '''
    # Check first name
    checkOne, checkTwo = False, False

    first_name = playName.split(" ")[0]
    if first_name in fullPlayer[1] or first_name in fullPlayer[2] or first_name in fullPlayer[0]["firstName"]:
        checkOne = True
    last_name = playName.split(" ")[-1]
    if last_name in fullPlayer[1] or last_name in fullPlayer[2] or last_name in fullPlayer[0]["lastName"]:
        checkTwo = True

    return checkOne and checkTwo



def compare_names(save=True, mlbjson="", sorarejson=""):
    '''
    Attempts to match names from Sorare Player Cards to those in the official baseball registry. Also classifies valid-matching players into their respective fielding categories.

    save: Saves output to a separate file on the disk.
    ...json: Respective JSON files for data
    '''

    cache = check_cache("./players-matched-registry.json")
    if cache: return cache

    # Load information into a dictionary
    mlb_registry_arr, mlb_registry = json.load(open(mlbjson)), dict()
    for player in mlb_registry_arr:
        mlb_registry[unidecode(player["name_first"] + " " + player["name_last"]).lower()] = player["key_mlbam"]
    sorare_arr = generate_names(sorarejson=sorarejson)

    print("Please wait, matching players from official registry to Sorare DB...")
    final_registry = dict() # Dict of lists [slug, positions-played object]
    for idx, player in enumerate(sorare_arr):
        # Attempt complete matching first.
        name = player[1]
        if name in mlb_registry:
            # Complete match found.
            final_registry[name] = [player[2], player[0]["positions"], mlb_registry[name]]
        else:
            for element in mlb_registry:
                if contains_some_match(element, player):
                    final_registry[element] = [player[2], player[0]["positions"], mlb_registry[element]]
                    break
        
        if idx % 50 == 0:
            print(idx, "players processed so far.")
    
    print("Successful!", len(final_registry), "players were successfully classified and matched.")

    dumped_registry = json.dumps(final_registry, indent=4)
    if save:
        with open("players-matched-registry.json", "w") as out:
            out.write(dumped_registry)
    print("Done! File is at players-matched-registry.json." if save else "Done!")

def separate_players_into_positions(save=True, filename=""):

    cache = check_cache("./players-filtered-result.json")
    if cache: return cache

    registry = json.load(open(filename))
    result = [dict() for _ in range(6)] # OF, IF, DH, C, SP, RP. Prefer OF > IF > DH > C, RP > SP
    for player in registry:
        # registry[player][1] is position object
        if "RELIEF_PITCHER" in registry[player][1]:
            result[5][player] = [registry[player][0], registry[player][2]]
        elif "STARTING_PITCHER" in registry[player][1]:
            result[4][player] = [registry[player][0], registry[player][2]]
        elif "OUTFIELD" in registry[player][1]:
            result[0][player] = [registry[player][0], registry[player][2]]
        elif "FIRST_BASE" in registry[player][1] or "SECOND_BASE" in registry[player][1] or "THIRD_BASE" in registry[player][1] or "SHORTSTOP" in registry[player][1]:
            result[1][player] = [registry[player][0], registry[player][2]]
        elif "DESIGNATED_HITTER" in registry[player][1]:
            result[2][player] = [registry[player][0], registry[player][2]]
        elif "CATCHER" in registry[player][1]:
            result[3][player] = [registry[player][0], registry[player][2]]

    dumped_result = json.dumps(result, indent=4)
    if save:
        with open("players-filtered-result.json", "w") as out:
            out.write(dumped_result)
    print("Done! File is at players-filtered-result.json." if save else "Done!")
    
def search_values_for_players(save=True, filename=""):
    
    filtered_result = json.load(open(filename))
    named_result = [dict() for _ in range(6)]
    for idx, category in enumerate(filtered_result):
        if idx < 4: batter = True
        else: batter = False

        ctr = 0
        slugs = [(category[player][0] + "-2023-limited-1", player) for player in category]
        while ctr < len(category):
            # Run GraphQL query here
            if batter:
                QUERY = """{
                    baseballCards(slugs: %s) {
                        player {
                            currentSeasonAverageScore{
                                batting
                            }
                        }
                    }
                }
                """ % (json.dumps([_[0] for _ in slugs[ctr:ctr + 50]]))
                js_obj = json.loads(requests.post(URL, headers={"APIKEY": APIKEY}, json={'query': QUERY}).text)
                for curr, value in enumerate(js_obj["data"]["baseballCards"]):
                    named_result[idx][slugs[ctr + curr][1]] = [value["player"]["currentSeasonAverageScore"]["batting"], category[slugs[ctr + curr][1]][1]]
            else:
                QUERY = """{
                    baseballCards(slugs: %s) {
                        player {
                            currentSeasonAverageScore{
                                pitching
                            }
                        }
                    }
                }
                """ % (json.dumps([_[0] for _ in slugs[ctr:ctr + 50]]))
                js_obj = json.loads(requests.post(URL, headers={"APIKEY": APIKEY}, json={'query': QUERY}).text)
                for curr, value in enumerate(js_obj["data"]["baseballCards"]):
                    named_result[idx][slugs[ctr + curr][1]] = [value["player"]["currentSeasonAverageScore"]["pitching"], category[slugs[ctr + curr][1]][1]]
            ctr += 50
    
    scores_and_ids = json.dumps(named_result, indent=4)
    if save:
        with open("scores_and_ids.json", "w") as out:
            out.write(scores_and_ids)
    print("Done! File is at scores_and_ids.json." if save else "Done!")

search_values_for_players(filename="./players-filtered-result.json")
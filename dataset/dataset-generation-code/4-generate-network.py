import numpy as np
import pandas as pd
import timeit

import re
import math

import datetime
from dateutil.relativedelta import relativedelta

import argparse
import sys
import os

#############################################################################################
# set some global variables
#############################################################################################

# Define relative location of resolved data files used in network generation
posts_file          = "forum/post.tsv"
forum_user_file     = "forum/user.tsv"
market_forum_user_matching_file = "forum-market/user-matching.tsv"

# Define relative locations generated network files
nodes_output_file = "network/nodes.tsv"
edges_output_file = "network/edges.tsv"

#############################################################################################
# Logger class functions
#############################################################################################

class Logger(object):
  def __init__(self):
    self.terminal = sys.stdout
    self.log = open("logfile-generate-network.log", "w")

  def write(self, message):
    self.terminal.write(message)
    self.log.write(message)

  def flush(self):
    # this flush method is needed for python 3 compatibility.
    # this handles the flush command by doing nothing.
    # you might want to specify some extra behavior here.
    pass

#############################################################################################
# Input parser class functions
#############################################################################################

class InputParser(object):
  def __init__(self):
    self.parser = argparse.ArgumentParser(description="Communication network extraction from resolved forum and market data. Command line arguments determine network created. Arguments indicating time must be presented in string format \".y.mo.d.h.min.s\", where the .'s should be replaced by integers indicating respectively how many years, months, days, hours, minutes, and seconds. Note, only the relevant parts of the string are required.")
    self.setArguments()
    self.printInput()

  def setArguments(self):
    self.parser.add_argument('-dir', "--inoutdir", required=True, help="Location of base directory containing output directories for resolved forum and market data, i.e., previous steps output directory. Will be used as both input and output directory here")

    self.parser.add_argument('-np', "--numposts", default=10, type=int, help="Number of posts we look back (at most) within topics to establish links")
    self.parser.add_argument('-mt', "--maxtimediff", default="1mo", type=str, help="Maximum time difference between posts allowed for links to be added")
    self.parser.add_argument('-mw', "--minweight", default=0.2, type=float, help="Minimum edge weight linking two posts (must be in range (0,1])")
    self.parser.add_argument('-tt', "--timetill", default="7d", type=str, help="Time difference beyond which all connections become minimum weight")
    self.parser.add_argument('-fp', "--firstpost", default=True, type=bool, help="Are links to the fist post of topic always included?")
    self.parser.add_argument('-fw', "--firstweight", default=0.5, type=float, help="Weight of links to first post of topics (must be in range (0,1])")
    self.parser.add_argument('-wp', "--weightprecision", default=5, type=int, help="Precision used for edge weights output")

  def getInputArgumentsAsDict(self):
    return vars(self.parser.parse_args())

  def printInput(self):
    args = self.getInputArgumentsAsDict()
    print("=======================")
    for label in args.keys():
      print("{}: {}".format(self.parser._option_string_actions["--" +label].help, args[label]))
    print("=======================\n")

#############################################################################################
# Functions to read in data
#############################################################################################

def readInDataDictOfDataframes(args):
  '''Read in all relevant resolved data into a dictionary of dataframes
  Parameters:
    args - dictionary of command line arguments given
  Returns: a dictionary of dataframes of the read in data
  '''
  return {"posts":         pd.read_csv(os.path.join(args["inoutdir"], posts_file),                      sep="\t", index_col=False),
          "users":         pd.read_csv(os.path.join(args["inoutdir"], forum_user_file),                 sep="\t", index_col=False),
          "user_matching": pd.read_csv(os.path.join(args["inoutdir"], market_forum_user_matching_file), sep="\t", index_col=False).dropna(subset=["uid"])}

#############################################################################################
# Network nodes generation functions
#############################################################################################

def getMaxTitle(var_set):
  ''' Determines and returns the most significant user title among the set defined by var_set
  Parameters:
    var_set - the set of user titles to pick from
  Returns: the most significant title among the set
  '''
  if "Administrator" in var_set:
    return "Administrator"
  elif "Market Moderator" in var_set:
    return "Market Moderator"
  elif "Forum Moderator" in var_set:
    return "Forum Moderator"
  elif "Moderator" in var_set:
    return "Moderator"
  elif "Public Relations" in var_set:
    return "Public Relations"
  elif "Banned" in var_set:
     return "Banned"
  elif "Vendor" in var_set:
    return "Vendor"
  elif "Resident Medical Expert" in var_set:
    return "Resident Medical Expert"
  elif "Troll" in var_set:
    return "Troll"
  elif "Member" in var_set:
    return "Member"
  elif "Guest" in var_set:
    return "Guest"
  elif "Sports Referee" in var_set:
    return "Sports Referee"
  elif "Sports Fan" in var_set:
     return "Sports Fan"
  else:
    print("Warning (99): title options yet to be included, option are {}".format(var_set))
    return "TODO"

def generateNodes(args, data):
  '''Generate nodes of the communication networks based on forum user identifiers. Additionally, determine those uid's
     with the same username and the first year and month that these users placed any post (as node attributes).
  Parameters:
    args - dictionary of command line arguments given
    data - dictionary of dataframes of resolved data
  Returns: a dataframe of the generated nodes and their attributes
  '''
  nodes = []
  for usn in sorted(data["users"]["username"].unique()):
    #print("Generating nodes of the network... username = {}".format(usn), end='\r')
    node_info = {"uid":None, "secondary_uid":None, "tertiary_uid":None, "match_id":None,
                 "init_year":None, "init_month":None}
    # Determine uids with matching username
    uids = sorted(list(data["users"].loc[data["users"]["username"] == usn]["uid"].unique()))
    node_info["uid"] = uids[0]
    if len(uids) > 1:
      node_info["secondary_uid"] = uids[1]
    if len(uids) > 2:
      node_info["tertiary_uid"] = uids[2]
    if len(uids) > 3:
      print("Error (1): there should not be cases with more than three uids for a given username. (usn = {}, uids = {})".format(usn, uids))
    # Determine match_id if a match with vendor was found during user matching
    match_ids = [x for x in data["user_matching"].loc[data["user_matching"]["username"] == usn]["match_id"].unique() if x == x]
    if len(match_ids) == 1:
      node_info["match_id"] = int(match_ids[0])
    elif len(match_ids) > 1:
      print("Error (2): there should not be cases with more than one match_id for a given username. (usn = {}, match_ids = {})".format(usn, match_ids))

    # Compute initial year + month of post placement for this node
    df_posts = data["posts"].loc[data["posts"]["uid"].isin(uids)].sort_values(["year", "month"], ascending=[True, True])
    if len(df_posts) > 0:
      node_info["init_year"] = df_posts.iloc[0]["year"]
      node_info["init_month"] = df_posts.iloc[0]["month"]

    nodes.append(node_info)

  # Store and return the dataframe with the generated nodes and their attributes
  df_nodes = pd.DataFrame(nodes).sort_values(["uid"], ascending=[True])
  df_nodes.to_csv(os.path.join(args["inoutdir"], nodes_output_file), sep='\t', float_format="%.0f", index=False)
  return df_nodes

#############################################################################################
# Network edges generation functions
#############################################################################################

def extractTimeFromArgument(arg):
  '''Read command line argument indicating a period of time into a dictionary
  Parameters:
    arg - command line argument indicating time that should be read into dictionary
  Returns: a dictionary specifying the years, months, days and seconds indicated by the argument
  '''
  years = re.findall(r"\d+?(?=y)", arg)
  months = re.findall(r"\d+?(?=mo)", arg)
  weeks = re.findall(r"\d+?(?=w)", arg)
  days = re.findall(r"\d+?(?=d)", arg)
  hours = re.findall(r"\d+?(?=h)", arg)
  minutes = re.findall(r"\d+?(?=min)", arg)
  seconds = re.findall(r"\d+?(?=s)", arg)
  time_arg = {"years":0, "months":0, "days":0, "seconds":0}
  if len(years) > 0:
    time_arg["years"] += int(years[0])
  if len(months) > 0:
    time_arg["months"] += int(months[0])
  if len(weeks) > 0:
    time_arg["days"] += int(weeks[0]) * 7
  if len(days) > 0:
    time_arg["days"] += int(days[0])
  if len(hours) > 0:
    time_arg["seconds"] += int(hours[0]) * 3600
  if len(minutes) > 0:
    time_arg["seconds"] += int(minutes[0]) * 60
  if len(seconds) > 0:
    time_arg["seconds"] += int(seconds[0])
  return time_arg

def getDateTimeFromDFEntry(entry):
  '''Create datetime object from entry
  Parameters:
    entry - a dataframe row containing the columns: year, month, day, and time (in the hh:mm:ss format)
  Returns: a datetime object set to the date and time specified in the entry parameter

  '''
  time_split = entry["time"].split(':')
  if entry["day"] == 0:
    print("Error (3): day = 0 should never occur. So if it does, fix it!")
    return datetime.datetime(year=entry["year"], month=entry["month"], day=1,
                           hour=int(time_split[0]), minute=int(time_split[1]), second=int(time_split[2]))
  #print(entry)
  date = datetime.datetime(year=entry["year"], month=entry["month"], day=entry["day"],
                           hour=int(time_split[0]), minute=int(time_split[1]), second=int(time_split[2]))
  return date

def getPrimaryNodeUID(df_nodes, uid):
  '''Determines the node identifier, i.e, primary node uid, for a given uid which may be listed as secondary or tertiary uid
  Parameters:
    df_nodes - dataframe of generated nodes and their attributes (including other uid's with the same username)
    uid      - the uid for which the primary node uid should be found in the dataframe
  Returns: the primary node uid corresponding to the 'uid' given as parameter
  '''
  if uid in df_nodes["uid"].unique():
    return uid
  elif uid in df_nodes["secondary_uid"].unique():
    return list(df_nodes.loc[df_nodes["secondary_uid"] == uid]["uid"])[0]
  else:
    return list(df_nodes.loc[df_nodes["tertiary_uid"] == uid]["uid"])[0]

def satisfiesTimeConstraint(mtd, time_now, time_prev):
  '''Determine whether the time constraint, limiting the time between two posts for an edge to exist, is met
  Parameters:
    mtd       - dictionary specifying the maximum amount of time between posts to form an edge allowed
                (required keys: years, months, days, and seconds)
    time_now  - datetime object specifying the placement time of the post from which an edge is formed (source node)
    time_prev - datetime object specifying the placement time of the post to which we an edge is formed (target node)
  Returns: boolean indicating whether time constraint for edge existence was met
  '''
  time_prev += relativedelta(years=mtd["years"], months=mtd["months"], days=mtd["days"], seconds=mtd["seconds"])
  if time_prev > time_now:
    return True
  return False

def computeWeight(args, ttl, time_now, time_prev):
  '''Computes the edge weight based on an exponential weighting function and the time difference between posts
  Parameters:
    args      - dictionary of command line arguments given
    ttl       - dictionary specifying the timeframe used in the exponential weighting function, with fields years, month, days, and seconds
    time_now  - datetime object specifying the placement time of the post from which an edge is formed (source node)
    time_prev - datetime object specifying the placement time of the post to which we an edge is formed (target node)
  Returns: a weight between minimum weight specified in args and 1, determined using an exponential weighting function
  '''
  time_till = time_prev + relativedelta(years=ttl["years"], months=ttl["months"], days=ttl["days"], seconds=ttl["seconds"])
  if time_till <= time_now:
    return args["minweight"]
  time_total_diff = time_till - time_prev
  time_till_till = time_till - time_now
  return args["minweight"] + (1-args["minweight"]) * \
         (math.exp(3*(time_till_till.total_seconds()/time_total_diff.total_seconds())) - 1)/(math.pow(math.e,3) - 1)

def generateMonthlyEdges(args, data, df_nodes):
  '''Generate all monthly communication network edges at the same time. Each monthly network is stored in their own file.
  Parameters:
    args     - dictionary of command line arguments given
    data     - dictionary of dataframes of resolved data
    df_nodes - dataframe of generated nodes and their attributes (including other uid's with the same username)
  '''
  mtd = extractTimeFromArgument(args["maxtimediff"])
  ttl = extractTimeFromArgument(args["timetill"])
  init_date = datetime.datetime(year=2014, month=1, day=1)

  # Generate edges on a forum topic by topic basis
  links = {"2014-1":[], "2014-2":[], "2014-3":[], "2014-4":[], "2014-5":[], "2014-6":[],
           "2014-7":[], "2014-8":[], "2014-9":[], "2014-10":[], "2014-11":[], "2014-12":[],
           "2015-1":[], "2015-2":[], "2015-3":[]}
  for tid in sorted(data["posts"]["tid"].unique()):
    print("Generating edges of the monthly networks... tid = {}".format(tid), end='\r')
    dft_posts = data["posts"].loc[data["posts"]["tid"] == tid].sort_values(["seq_id"], ascending=[True])

    # First we generate the edges linking each poster to the initial poster of the topic
    if args["firstpost"]:
      init_post = dft_posts.iloc[0]
      init_uid = getPrimaryNodeUID(df_nodes, init_post["uid"])
      init_time = getDateTimeFromDFEntry(init_post)
      for i in range(1, len(dft_posts)):
        post_i = dft_posts.iloc[i]
        uid_i = getPrimaryNodeUID(df_nodes, post_i["uid"])
        if uid_i != init_uid: # We don't create self-edges
          time_i = getDateTimeFromDFEntry(post_i)
          link_info = {"Source":uid_i, "Target":init_uid, "Weight":args["firstweight"],               # Basic edge information
                       "to_first":True, "time_diff":(time_i-init_time).total_seconds(), "seq_diff":i, # Variables to explain weight
                       "timestamp":(time_i-init_date).total_seconds(), "tid":tid}          # other information
          # We add the edge to each network from the month that post_i was placed
          if time_i.year == 2014:
            for m in range(time_i.month,13):
              links['2014-' + str(m)].append(link_info)
            for m in range(1,4):
              links['2015-' + str(m)].append(link_info)
          else:
            for m in range(time_i.month,4):
              links['2015-' + str(m)].append(link_info)

    # Next we generate the edges connecting users posting at most 'numposts' posts apart and 'maxtimediff' apart
    for i in reversed(range(1,len(dft_posts))):
      current_post = dft_posts.iloc[i]
      current_uid = getPrimaryNodeUID(df_nodes, current_post["uid"])
      current_time = getDateTimeFromDFEntry(current_post)
      # We consider creating edges from the current post only to the 'numposts' most recent previous posts
      for j in reversed(range(max(0,i-args["numposts"]),i)):
        previous_post = dft_posts.iloc[j]
        previous_uid = getPrimaryNodeUID(df_nodes, previous_post["uid"])
        previous_time = getDateTimeFromDFEntry(previous_post)
        # If we have arrived at the same users' previous post or too much time has passed, we stop generating edges for this current post
        if previous_uid == current_uid or not satisfiesTimeConstraint(mtd, current_time, previous_time):
          break
        # If all conditions are met, a weight is computed and the edge is created
        weight = computeWeight(args, ttl, current_time, previous_time)
        link_info = {"Source":current_uid, "Target":previous_uid, "Weight":weight,                                # Basic edge information
                     "to_first":False, "time_diff":(current_time-previous_time).total_seconds(), "seq_diff":i-j,  # Variables to explain weight
                     "timestamp":(current_time-init_date).total_seconds(), "tid":tid}                             # other information
        # We add the edge to each network from the month that current_post was placed
        if current_time.year == 2014:
          for m in range(current_time.month,13):
            links['2014-' + str(m)].append(link_info)
          for m in range(1,4):
            links['2015-' + str(m)].append(link_info)
        else:
          for m in range(current_time.month,4):
            links['2015-' + str(m)].append(link_info)

  # We output monthly edge networks
  for label, month_links in links.items():
    df_monthly_edges = pd.DataFrame(month_links).sort_values(["Source", "Target", "timestamp"], ascending=[True, True, False])
    # Adjust edge weights to desired precision
    df_monthly_edges["Weight"] = df_monthly_edges["Weight"].map(lambda x: '{0:.{1}f}'.format(x, args["weightprecision"]).rstrip('0'))
    df_monthly_edges.to_csv(os.path.join(args["inoutdir"], edges_output_file[:-4] + '-' + label + ".tsv"), sep='\t', float_format="%.0f", index=False)

#############################################################################################
# Main functions
#############################################################################################

if __name__ == "__main__":
  sys.stdout = Logger()
  start_time = timeit.default_timer()

  # Process command line input
  input_parser = InputParser()
  args = input_parser.getInputArgumentsAsDict()
  os.makedirs(os.path.join(args["inoutdir"], "network"), exist_ok=True)

  print("Reading in data...", end='\r')
  data = readInDataDictOfDataframes(args)
  print("Reading in data... DONE")

  print("Generating nodes of the network...", end='\r')
  df_nodes = generateNodes(args, data)
  print("Generating nodes of the network... DONE           ")

  print("Generating edges of (monthly) network(s)...", end='\r')
  generateMonthlyEdges(args, data, df_nodes)
  print("Generating edges of (monthly) network(s)... DONE              ")

  stop_time = timeit.default_timer()
  print("Total runtime: {}s".format(stop_time - start_time))
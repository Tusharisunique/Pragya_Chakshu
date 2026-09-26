import numpy as np
import pandas as pd
import timeit

import re

import math
import shutil
import argparse
import sys
import os
import datetime as dt

#############################################################################################
# set some global variables
#############################################################################################

# output information splitters
scrape_splitter = "================================="

# File names used for both input and outputting preprocessed data
scrapes_file     = "scrapes.tsv"
index_file       = "global-stats.tsv"
index_fora_file  = "index-forum.tsv"
fora_file        = "forum.tsv"
fora_topic_file  = "forum-topic.tsv"
topics_file      = "topic.tsv"
posts_file       = "post.tsv"
quotes_file      = "quote.tsv"
profile_file     = "user.tsv"

MAX_TOPIC_DELETION = 10  # When more than MAX_TOPIC_DELETION topics are 'deleted' between two subsequent scrapes AND the number of expected topics (and found topics) are equal to pages*30, then we assume that something went wrong and that the scrape was simply incomplete! As such we skip this scrape for the computation of the 'new_topics' variable


#############################################################################################
# Logger functions
#############################################################################################

class Logger(object):
  def __init__(self):
    self.terminal = sys.stdout
    self.log = open("logfile-preproc-forum.log", "w")

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
    self.parser = argparse.ArgumentParser(description="Preprocesses extracted forum data by combining the various data sources and resolving various data quality issues. Resultant data is stored in specified output directory.")
    self.setArguments()
    self.printInput()

  def setArguments(self):
    self.parser.add_argument('-in', "--indir", required=True, help="Location of base directory where extracted data was stored during previous step, i.e., previous output directory")
    self.parser.add_argument('-out', "--outdir", required=True, help="Location of base directory where preprocessed and resolved data should be stored")

  def getInputArgumentsAsDict(self):
    return vars(self.parser.parse_args())

  def printInput(self):
    args = self.getInputArgumentsAsDict()
    print(scrape_splitter)
    for label in args.keys():
      print("{}: {}".format(self.parser._option_string_actions["--" +label].help, args[label]))
    print(scrape_splitter + "\n")


#############################################################################################
# Helper functions
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
    print("Warning (99): title options yet to be included, options are {}".format(var_set))
    return "TODO"

#############################################################################################
# General (i.e., non-specific) conflict resolution functions
#############################################################################################

def determineConflicts(dfus, var):
  '''Among the entries in the dataframes 'dfus' for variable 'var' determine all possible values
  Parameters:
    dfus - a list of dataframes each with a column corresponding to 'var'
    var  - column name of the variable for which the possible options are to be determined
  Returns: a list of all possible values of the variable found among the dataframes

  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x}
  return list(var_set)

def resolveDateConflict(dfus, vars_dict, warning_info):
  '''Determine and resolve date conflicts
  Parameters:
    dfus         - list of dataframes with year, month, and day columns corresponding to names defined by 'vars_dict'
    vars_dict    - dictionary defining the column names for the year, month, and day
    warning_info - warning message to be displayed in case such a warning is applicable
  Returns: datetime object with the resolved data, usually the earliest date

  '''
  dates = []
  # Determine all date options
  df_reduc = pd.concat([dfu[[vars_dict["year"], vars_dict["month"], vars_dict["day"]]] for dfu in dfus], ignore_index=True).drop_duplicates().dropna()
  for i in range(len(df_reduc)):
    new_date = dt.date(int(df_reduc.iloc[i][vars_dict["year"]]),
                       int(df_reduc.iloc[i][vars_dict["month"]]),
                       int(df_reduc.iloc[i][vars_dict["day"]]))
    dates.append(new_date)
  # Resolve possible date conflicts
  if len(dates) == 1: # only one option
    return dates[0]
  elif len(dates) == 2: # Exactly two options, if one day difference this is due to mistaken modification date as obtained from file metadata
    if dates[0] < dates[1]:
      if dates[1] - dt.timedelta(days=1) == dates[0]:
        return dates[0]
    elif dates[0] - dt.timedelta(days=1) == dates[1]:
      return dates[1]
    # If the difference is greater than 1 day, we are dealing with a different type of error.
    # In those cases we check if the minimum date matches the most frequent, if so we choose that date.
    min_date = min(dates)
    freq_1 = 0
    freq_2 = 0
    for df in dfus:
      freq_1 += len(df.loc[(df[vars_dict["year"]] == dates[0].year) & (df[vars_dict["month"]] == dates[0].month) & (df[vars_dict["day"]] == dates[0].day)])
      freq_2 += len(df.loc[(df[vars_dict["year"]] == dates[1].year) & (df[vars_dict["month"]] == dates[1].month) & (df[vars_dict["day"]] == dates[1].day)])
    if (freq_1 >= freq_2 and min_date == dates[0]) or (freq_1 <= freq_2 and min_date == dates[1]):
      return min_date
    else: # Never happens in practice
      print("Warning (1): two dates found more than 1 day apart and most frequent did not match minimum for {}. Options are {} with frequencies {} and {}. Earliest ({}) returned.".format(warning_info, dates, freq_1, freq_2, min_date))
      return min_date
  else: # If there are more than 2 dates, we simply take the minimum date (as errors are much more likely to be higher)
    print("Warning (2): Unexpectedly more than 2 possible dates for {}. Options are {}. Earliest ({}) returned".format(warning_info, dates, min(dates)))
    # In practice the minimum date here was found to always be the correct one
    return min(dates)

def resolveUserConflicts(df_users, df, uid_var, username_var, edit_or_last_flag, warning_info):
  '''Resolve username, uid conflicts with previously resolved user data.
  Parameters
    df_users          - dataframe with already resolved forum user information for all users
    df                - dataframe with uid/username information for which we want to resolve possible conflicts
                        with already resolved user information such that the correct version is used
    uid_var           - column name for the uid in the dataframes
    useranme_var      - column name for the username in the dataframes
    edit_or_last_flag - flag indicating whether we are considering edit or last post user information
    warning_info      - warning message to be displayed in case such a warning is applicable
  Returns: chosen uid and username combination (as strings)
  '''
  uid = None
  usn = None
  # Retrieve the uid and username options
  uids = []

  if edit_or_last_flag: # Multiple users may have edited a post or may be considered the 'last poster', we wish to only store the latest
    usernames = [df[[username_var, "scrape_id"]].dropna().sort_values(["scrape_id"], ascending=[False]).reset_index(drop=True)[username_var][0]]
  else:
    uids = [x for x in df[uid_var].unique() if x==x]# if str(x) != "nan"]
    usernames = [x for x in df[username_var].unique() if x==x]# if str(x) != "nan"]
  if len(uids) == 1: # Utilize our earlier resolving of user information for this specific uid (should never fail!)
    uid = uids[0]
    username_match = df_users.loc[df_users["uid"] == uids[0]]["username"].unique()[0]
    usn = username_match
  elif len(uids) == 0:
    if len(usernames) == 1: # If no uid's known, utilise known username to retrieve appropriate uid
      usn = usernames[0]
      uid_match = df_users.loc[df_users["username"] == usernames[0]]["uid"].unique()
      if len(uid_match) > 0:
        uid = max(uid_match) # A user may have been banned and started a new uid with the same username (Around 40 occurrences of this exist! Though not all of those also have posts.)
      else: # check for known name changes, that are therefore logically not in the df_users table
        if usn == "dredknotz":
          uid = 232
          usn = "LinQue"
        elif usn == "only_bak":
          uid = 497
          usn = "only"
        elif usn == "loste":
          uid = 1936
          usn = "lot_oo7"
        elif usn == "ShadyTom":
          uid = 1977
          usn = "Luxor"
        elif usn == "ozzyz":
          uid = 7082
          usn = "Ozzyz"
        else:
          print("Warning (3): no uid matches for uid {} for {}".format(usn, warning_info))
          #new_users.add(post_info["username"])
    elif len(usernames) > 1: # No uid known, and multiple username options. Doesn't seem to ever occur
      if "LinQue" in usernames:
        uid = 232
        usn = "LinQue"
      elif "only_bak" in usernames:
        uid = 497
        usn = "only"
      elif "lot_oo7" in usernames:
        uid = 1936
        usn = "lot_oo7"
      elif "Luxor" in usernames:
        uid = 1977
        usn = "Luxor"
      elif "Ozzyz" in usernames:
        uid = 7082
        usn = "Ozzyz"
      else:
        print("Warning (4): No uid known and multiple usernames but no a known exception case for {}. Options for username are {}".format(warning_info, usernames))
    else: # Neither uid or usernames are known. Doesn't seem to actually ever occur
      print("Warning (5): Neither usernames nor uids found for {}".format(warning_info))
  else: # In case there are multiple uid's registered, check which uid matches expected username(s)
    username_matches = set()
    for uid in uids:
      username_matches.add(df_users.loc[df_users["uid"] == uid]["username"].unique()[0])
    if len(username_matches) == 1 and (len(usernames) == 0 or list(username_matches)[0] in usernames):
      usn = list(username_matches)[0]
      uid = max(uids)
    else: # Too many username options or mismatch with known usernames. Doesn't seem to actually ever occur
      print("Warning (6): Mismatch usernames and uid matched usernames... username_matches = {}, usernames = {}, uids = {}, for {}".format(username_matches, usernames, uids, warning_info))
  return str(int(uid)), usn

#############################################################################################
# Functions for preprocessing data regarding the scrapes
#############################################################################################

def preprocessScrapeData(args):
  '''Combine information on scrapes gathered from scrape directory names with statistics obtained from index pages
  Parameters:
    args - dictionary of command line arguments given
  Returns:
    df_merge - dictionary storing the merged information on each of the scrapes
  '''
  df_scrapes = pd.read_csv(os.path.join(args["indir"], scrapes_file), sep='\t', index_col=False)
  df_index = pd.read_csv(os.path.join(args["indir"], index_file), sep='\t', index_col=False)

  df_merge = pd.merge(df_scrapes, df_index, on=["scrape_id"], how="inner").drop(columns="error")
  df_merge.to_csv(os.path.join(args["outdir"], "forum", scrapes_file), sep='\t', float_format="%.0f", index=False)
  return df_merge

#############################################################################################
# Functions for preprocessing data regarding the fora
#############################################################################################

def resolveForumConflicts(dfus, info, var):
  ''' Determines whether there are any conflicts for a given variable and (if known) resolves them
  Parameters:
    dfus  - List of panda dataframes within which the variable must be checked for conflicts
    info  - Dictionary in which the resolved variable must be stored
    var   - Variable (string) for which conflicts must be checked
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x}
  if len(var_set) > 1:
    if var in ["topics", "error"]:
      info[var] = max(var_set)
    else:
      print("Error (1): multiple {}s detected for fid {} and scrape {}. Options are: {}".format(var, info["fid"], info["scrape_id"], var_set))
  elif len(var_set) != 0:
    info[var] = list(var_set)[0]

def checkResolvedForumErrors(info):
  '''Check if error information stored was not already resolved by information pulled from different extracted sources
  Parameters:
    info - a dictionary storing information on the current forum under consideration
  '''
  if info["error"] == 99 and info["topics_complete"]:
    info["error"] = None

def preprocessForaData(args, df_scrape, df_posts, df_topics):
  '''Preprocess forum forum data by combining extracted data on them and resolving any conflicts.
      Additionally, computes some statistics w.r.t. completeness for each forum based on already resolved topic and post data.
  Parameters:
    args      - dictionary of command line arguments given
    df_scrape - dataframe storing already resolved forum scrape information
    df_posts  - dataframe storing already resolved forum post information
    df_topics - dataframe storing already resolved forum topic information
  '''
  # Retrieve all forum related extracted data
  df_index_fora = pd.read_csv(os.path.join(args["indir"], index_fora_file), sep='\t', index_col=False)
  df_fora = pd.read_csv(os.path.join(args["indir"], fora_file), sep="\t", index_col=False)
  fids = set(df_fora["fid"].unique()).union(set(df_topics["fid"].unique())).union(set(df_index_fora["fid"].unique()))

  # Preprocess fora one forum identifier at a time
  all_fora = []
  for fid in sorted(fids):
    print("Now processing fid {}".format(fid), end='\r')
    dff_index_fora = df_index_fora.loc[df_index_fora["fid"] == fid]
    dff_fora = df_fora.loc[df_fora["fid"] == fid]
    dff_topics = df_topics.loc[df_topics["fid"] == fid]

    # Preprocess for each scrape separately
    sids = set(dff_fora["scrape_id"].unique()).union(set(dff_topics["scrape_id"].unique())).union(set(dff_index_fora["scrape_id"].unique()))
    prev_topics = None; prev_posts = None
    for sid in sorted(sids):
      dffs_index_fora = dff_index_fora.loc[dff_index_fora["scrape_id"] == sid]
      dffs_fora = dff_fora.loc[dff_fora["scrape_id"] == sid]
      dffs_topics = dff_topics.loc[dff_topics["scrape_id"] <= sid]

      forum_info = {"fid":fid, "scrape_id":sid, "category":None, "title":None, "description":None, "pages":None,
                    "topics":None, "topics_visible":None, "topics_found":None,
                    "posts":None, "posts_found":None,
                    "error":None}

      # Resolve basic information about forum
      resolveForumConflicts([dffs_index_fora], forum_info, "category")
      resolveForumConflicts([dffs_index_fora, dffs_fora], forum_info, "title")
      resolveForumConflicts([dffs_index_fora], forum_info, "description")
      resolveForumConflicts([dffs_fora], forum_info, "pages")
      resolveForumConflicts([dffs_index_fora, dffs_fora], forum_info, "topics")
      resolveForumConflicts([dffs_fora], forum_info, "topics_visible")
      # Determine number of topics actually found in extracted data
      forum_info["topics_found"] = len(dffs_topics["tid"].unique())

      # Determine post statistics
      resolveForumConflicts([dffs_index_fora], forum_info, "posts")
      # Determine how many posts (from any scrape) were found for the topics found up to this scrape's point in time
      scrape = df_scrape.loc[df_scrape["scrape_id"] == sid].iloc[0]
      scrape_date = dt.date(scrape["scrape_year"], scrape["scrape_month"], scrape["scrape_day"])
      dft_posts = df_posts.loc[df_posts["tid"].isin(list(dffs_topics["tid"].unique()))].sort_values(["year", "month", "day"], ascending=[True, True, True]).reset_index(drop=True)
      num_posts_ontime = -1
      for i in reversed(range(len(dft_posts))):
        post = dft_posts.iloc[i]
        post_date = dt.date(post["year"], post["month"], post["day"])
        if post_date <= scrape_date:
          num_posts_ontime = i+1
          break
      if num_posts_ontime == -1:
       forum_info["posts_found"] = 0 # Only occurs the one time that there are also just 0 topics to begin with
      else:
        forum_info["posts_found"] = num_posts_ontime

      resolveForumConflicts([dffs_index_fora, dffs_fora], forum_info, "error")
      all_fora.append(forum_info)

  # Store the resolved forum forum data. The error information is dropped for the final dataset
  df_fora_pp = pd.DataFrame(all_fora).drop(columns="error")
  df_fora_pp.to_csv(os.path.join(args["outdir"], "forum", fora_file), sep='\t', float_format="%.0f", index=False)

#############################################################################################
# Functions for preprocessing data on topics
#############################################################################################

def resolveTopicConflicts(dfus, info, var):
  ''' Determines whether there are any conflicts for a given variable and (if known) resolves them
  Parameters:
    dfus  - List of panda dataframes within which the variable must be checked for conflicts
    info  - Dictionary in which the resolved variable must be stored
    var   - Variable (string) for which conflicts must be checked
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x}
  if len(var_set) > 1:
    if var in ["num_posts", "views"]:
      info[var] = max(var_set)
    else:
      print("Error (3): multiple {}s detected for tid {} and scrape {}. Options are: {}".format(var, info["tid"], info["scrape_id"], var_set))
      print(dfus)
  elif len(var_set) != 0:
    info[var] = list(var_set)[0]


def checkResolvedTopicErrors(info):
  '''Check if error information stored was not already resolved by information pulled from different extracted sources
  Parameters:
    info - a dictionary storing information on the current topic under consideration
  '''
  if info["error"]:
    if info["error"] == 22 and info["fid"]: # Check if the error indicates no forum id found, while we did find one elsewhere
      info["error"] = None
    if info["error"] in [21, 23]: # On topic or fid conflict the last retrieved was always chosen. No need to propagate the fact that a conflict existed, right?
      info["error"] = None

def preprocessTopicData(args, df_scrape, df_users, df_posts):
  '''Preprocesses topic data by combining extracted data on them and resolving any conflicts.
     Additionally, computes some statistics w.r.t. completeness for each topic based on already resolved post data.
  Parameters:
    args      - dictionary of command line arguments given
    df_scrape - dataframe storing already resolved forum scrape information
    df_users  - dataframe storing already resolved forum user information
    df_posts  - dataframe storing already resolved forum post information
  Returns: a dataframe with combined and resolved forum topic information
  '''
  # Retrieve all topic related extracted data
  df_topic = pd.read_csv(os.path.join(args["indir"],topics_file), sep="\t", index_col=False)
  df_topic.columns = ["tid", "title", "retrieval_time", "fid", "scrape_id", "num_posts", "new_posts",
                      "complete", "visible_pre", "visible_post", "visible", "error"]
  df_forum_topic = pd.read_csv(os.path.join(args["indir"],fora_topic_file), sep="\t", index_col=False)
  df_forum_topic["replies"] += 1 # Because 'replies' implies that it doesn't count the initial post!
  df_forum_topic.columns = ["fid", "tid", "title", "retrieval_time", "first_user", "first_uid", "first_found",
                            "scrape_id", "num_posts", "views", "tpid",
                            "lp_user", "lp_uid", "lp_year", "lp_month", "lp_day", "lp_time",
                            "closed", "moved", "error"]

  # Determine list of all topic identifiers for which we have some data
  tids = list(df_topic["tid"].unique())
  for tid in df_forum_topic["tid"].unique():
    if tid not in tids:
      tids.append(tid)

  # Preprocess topics one topic identifier at a time
  topics = []
  for tid in sorted(tids):
    print("Now processing tid {}".format(tid), end="\r")
    dft_top = df_topic.loc[df_topic["tid"] == tid]
    dft_for = df_forum_topic.loc[df_forum_topic["tid"] == tid]
    dft_posts = df_posts.loc[df_posts["tid"] == tid].sort_values(["year", "month", "day"], ascending=[True, True, True])

    # Resolve first user information, i.e, information on who placed the first post in the topic
    f_uid = None
    f_user = None
    if len(dft_for.dropna(subset=["first_user"])) > 0:
      f_uid, f_user = resolveUserConflicts(df_users, dft_for, "first_uid", "first_user", False, "tid {} (first)".format(tid))

    # Preprocess for each scrape separately
    ff = -1
    prev_posts = 0; prev_views = 0
    for sid in sorted(list(df_scrape["scrape_id"].unique())):
      dfts_top = dft_top.loc[dft_top["scrape_id"] == sid]
      dfts_for = dft_for.loc[dft_for["scrape_id"] == sid].sort_values(["lp_year", "lp_month", "lp_day", "lp_time"], ascending=[True, True, True, True])

      # Considering a topic can be 'moved', it is possible for fid's to change over time, and we don't want to throw that information away. As such we keep an entry for each fid
      fids = determineConflicts([dfts_top, dfts_for], "fid")
      if len(fids) == 0: # No information exists for this topic in this scrape
        continue
      if ff == -1: # Determine if this is the first scrape where we find information for this topic (not kept in final dataset)
        ff = sid

      # We retrieve the title based on the latest retrieval time
      titles = determineConflicts([dfts_top, dfts_for], "title")
      if len(titles) == 0:
        print("Warning (11): no title found for topic {} in scrape {}".format(tid, sid))
        title =  None
      elif len(titles) > 1:
        print("Warning (12): conflicting titles, latest found used for topic {} in scrape {}".format(tid, sid))
        title_options = pd.concat([dfts_top[["title", "retrieval_time"]], dfts_for[["title", "retrieval_time"]]], ignore_index=True).drop_duplicates().sort_values(["retrieval_time"], ascending=[False]).reset_index(drop=True) # Ascending false sets latest retrieval time first
        title = title_options["title"][0]
      else:
        title = titles[0]

      topic_info = {"fid":None, "tid":tid, "first_uid":f_uid, "first_user":f_user, "first_found":ff,
                    #"scrape_id":sid, "title":title, "num_posts":None, "new_posts":None, "views":None, "new_views":None,
                    "scrape_id":sid, "title":title, "num_posts":None, "visible":None, "posts_found":None, "views":None,
                    "lp_uid":None, "lp_user":None, "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                    "closed":None, "moved":None,
                    #"complete":None, "visible_pre":None, "visible_post":None, "visible":None
                    "error":None}


      # Resolve conflicts for the number of posts, views and how many posts were 'visible', i.e., are in the extracted data
      resolveTopicConflicts([dfts_top, dfts_for], topic_info, "num_posts")
      resolveTopicConflicts([dfts_for], topic_info, "views")

      resolveTopicConflicts([dfts_top], topic_info, "visible")
      if topic_info["visible"] is None:
        topic_info["visible"] = 0

      # Determine how many posts (from any scrape) were found for this topic found up to this scrape's point in time
      scrape = df_scrape.loc[df_scrape["scrape_id"] == sid].iloc[0]
      scrape_date = dt.date(scrape["scrape_year"], scrape["scrape_month"], scrape["scrape_day"])

      num_posts_ontime = 0
      for i in reversed(range(len(dft_posts))):
        post = dft_posts.iloc[i]
        post_date = dt.date(post["year"], post["month"], post["day"])
        if post_date <= scrape_date:
          num_posts_ontime = i+1
          break
      if num_posts_ontime == -1:
        topic_info["posts_found"] = 0 # Only occurs the one time that there are also just 0 topics to begin with
      else:
        topic_info["posts_found"] = num_posts_ontime

      # If at least one post was determined to have been placed, try to determine last post information
      if topic_info["num_posts"] is not None:
        # If last post information exist, extract poster and post time details
        dfts_for_reduc = dfts_for.dropna(subset=["lp_user"]) # drop any rows without last post information (dfts_for is already sorted accordingly)
        if len(dfts_for_reduc) > 0: # if there is any information on last posts, then we always take the 'last' information
          topic_info["lp_user"]  = dfts_for_reduc.iloc[-1]["lp_user"]
          topic_info["lp_year"]  = dfts_for_reduc.iloc[-1]["lp_year"]
          topic_info["lp_month"] = dfts_for_reduc.iloc[-1]["lp_month"]
          topic_info["lp_day"]   = dfts_for_reduc.iloc[-1]["lp_day"]
          topic_info["lp_time"]  = dfts_for_reduc.iloc[-1]["lp_time"]
        if topic_info["lp_user"]:
          uid_match = df_users.loc[df_users["username"] == topic_info["lp_user"]]["uid"].unique()
          if len(uid_match) > 0:
            topic_info["lp_uid"] = max(uid_match) # A user may have been banned and started a new uid with the same username (Around 37 occurrences of this exist! Though not all of those also have posts.)
          else: # check for known name changes, that are therefore logically not in the df_users table
            if topic_info["lp_user"] == "dredknotz":
              topic_info["lp_uid"] = 232
              topic_info["lp_user"] = "LinQue"
            elif topic_info["lp_user"] == "only_bak":
              topic_info["lp_uid"] = 497
              topic_info["lp_user"] = "only"
            elif topic_info["lp_user"] == "loste":
              topic_info["lp_uid"] = 1936
              topic_info["lp_user"] = "lot_oo7"
            elif topic_info["lp_user"] == "ShadyTom":
              topic_info["lp_uid"] = 1977
              topic_info["lp_user"] = "Luxor"
            elif topic_info["lp_user"] == "ozzyz":
              topic_info["lp_uid"] = 7082
              topic_info["lp_user"] = "Ozzyz"
            else:
              print("Warning (13): This username does not exist in df_users yet {} for tid = {} and sid = {}".format(topic_info["lp_user"], tid, sid))

      # For each forum identifier (fid) that information was found in this scrape for the topic, we store information
      for fid in fids:
        topic_info_fid = topic_info.copy()
        topic_info_fid["fid"] = fid
        dftf_for = dfts_for.loc[dfts_for["fid"] == fid]
        dftf_top = dfts_top.loc[dfts_top["fid"] == fid]
        # Resolve whether the topic was closed or moved for this fid
        resolveTopicConflicts([dftf_for], topic_info_fid, "closed")
        resolveTopicConflicts([dftf_for], topic_info_fid, "moved")
        if topic_info_fid["moved"] is None and len(dftf_top) > 0:
          # In this case we were able to retrieve this topic without having found it in forum pages, as such we can assume it was not moved (we can however not know whether it was closed or not)
          topic_info_fid["moved"] = False
        # Resolve error information, by checking if the supposedly missing information was not found through other sources (not kept)
        resolveTopicConflicts([dfts_top, dftf_for], topic_info_fid, "error")
        checkResolvedTopicErrors(topic_info_fid)
        topics.append(topic_info_fid)

  # Store and return a dataframe with the resolved forum topic data. The error information is dropped for the final dataset
  # Additionally, first and last post username information is dropped as this can be retrieved through the uid from the user information
  df_topics = pd.DataFrame(topics)
  df_topics.columns = ["fid", "tid", "first_uid", "first_user", "first_found","scrape_id", "title",
                       "posts", "posts_visible", "posts_found", "views",
                       "lp_uid", "lp_user", "lp_year", "lp_month", "lp_day", "lp_time",
                       "closed", "moved", "error"]
  df_topics = df_topics.drop(columns=["first_user", "first_found", "lp_user", "error"])
  df_topics.to_csv(os.path.join(args["outdir"], "forum", topics_file), sep='\t', float_format="%.0f", index=False)
  return df_topics

#############################################################################################
# Functions for preprocessing data on posts
#############################################################################################

def getPostData(args, df_scrape):
  '''Gather all posts and sort them ascending by topic id, then post id and then scrape_id
  Parameters:
    args       - dictionary of command line arguments given
    df_scrape  - pandas dataframe that stores the scrape information on the forum
  Returns: sorted pandas dataframe of all posts (approximately 4.7GB of memory usage required)
  '''
  #
  scrape_dfs = []
  for scrape_id in df_scrape.index:
    scrape_post_file = os.path.join(args["indir"], posts_file[:-4] + "-scrape-" + str(scrape_id) + ".tsv")
    scrape_dfs.append(pd.read_csv(scrape_post_file, sep='\t', index_col=False))
  return pd.concat(scrape_dfs).sort_values(["tid", "pid", "scrape_id"], ascending=[True, True, True]).reset_index(drop=True)

def preprocessPostData(args, df_users):
  '''Preprocess post data by selecting latest version of post and resolving any conflicts (using also the already resolved user data)
  Parameters:
    args      - dictionary of command line arguments given
    df_users  - dataframe storing already resolved user information
  Returns: a dataframe with the combined and resolved forum post information
  '''
  df_scrape = pd.read_csv(os.path.join(args["indir"], scrapes_file), sep="\t", index_col=0)
  df_posts = getPostData(args, df_scrape) # This comes pre-sorted such that we have no need to do that afterwards
  topics = df_posts["tid"].unique()

  # Preprocess all posts on a topic per topic basis
  topic_collection = []
  gaps_found = 0
  gap_cumulative_size_found = 0
  gap_tids = set()
  for tid in sorted(topics):
    print("Now processing tid {}".format(tid), end="\r")
    df_tid = df_posts.loc[df_posts["tid"] == tid]

    # Preprocess posts
    post_collection = []
    prev_seq = 0
    for pid in sorted(df_tid["pid"].unique()): # although a sorted list should already be returned, we double check this
      # Note, for posts we only care about their final form, although we do store when and by whom it was (last) edited.
      # We do this as it is unlikely that we will ever want to analyse changes in the text introduced by edits
      post_info = {"tid":tid, "pid":pid, "seq_id":None, "year":None, "month":None, "day":None, "time":None, 
                   "uid":None, "username":None,
                   "text":None, "signature":None, 
                   "edit_uid":None, "edit_username":None, "edit_year":None, "edit_month":None, "edit_day":None, "edit_time":None,
                   "error": None}
      df = df_tid.loc[df_tid["pid"] == pid]

      # Resolve post date + time
      date = resolveDateConflict([df], {"year":"year", "month":"month", "day":"day"}, "tid {}, pid {}".format(tid, pid))
      post_info["year"] = date.year
      post_info["month"] = date.month
      post_info["day"] = date.day
      times = [x for x in df["time"].unique() if x==x]
      if len(times) == 1:
        post_info["time"] = times[0]
      else: # Doesn't seem to actually ever occur
        if len(times) > 1:
          post_info["time"] = df.iloc[-1]["time"]
        print("Warning (7): tid = {}, pid = {}, times = {}".format(tid, pid, times))

      # Resolve poster credentials
      post_info["uid"], post_info["username"] = resolveUserConflicts(df_users, df, "uid", "username", False, "tid {}, pid {}".format(tid, pid))
      # Resolve text
      texts = [x for x in df["text"].unique() if x==x]
      if len(texts) == 1:
        post_info["text"] = texts[0]
      elif len(texts) > 1: # Since text is never missing, we can simply take the text from the last row as being the last version
        post_info["text"] = df.iloc[-1]["text"]
      else: # Doesn't seem to actually ever occur
        print("Warning (8): Text of posts never recorded for pid {} and tid {}".format(pid, tid))
      # Resolve signature
      signatures = [x for x in df["signature"].unique() if x==x]
      if len(signatures) == 1:
        post_info["signature"] = signatures[0]
      elif len(signatures) > 1: # NaN is possible for the signature, find bottom most row where signature is not NaN
        df_temp = df[df["signature"].notna()]
        post_info["signature"] = df_temp.iloc[-1]["signature"]
      
      # Resolve edit information
      df_edit = df[df["edit_username"].notna()]
      if len(df_edit) > 0:
        # Resolve edit user information
        post_info["edit_uid"], post_info["edit_username"] = resolveUserConflicts(df_users, df_edit, None, "edit_username", True, "tid {}, pid {} (edit)".format(tid, pid))
        # Resolve edit date + time to use the last version (i.e., to match the last edit)
        edit_years = [x for x in df_edit["edit_year"].unique() if x==x]
        edit_months = [x for x in df_edit["edit_month"].unique() if x==x]
        edit_days = [x for x in df_edit["edit_day"].unique() if x==x]
        edit_times = [x for x in df_edit["edit_time"].unique() if x==x]
        if len(edit_years) + len(edit_months) + len(edit_days) == 3:
          post_info["edit_year"] = str(int(edit_years[0]))
          post_info["edit_month"] = str(int(edit_months[0]))
          post_info["edit_day"] = str(int(edit_days[0]))
        else: # Note, since edit year, month, and day are never missing (NaN), we can take the value of the bottom row as the 'last' value
          if len(edit_years) < 1 or len(edit_months) < 1 or len(edit_days) < 1:  # Doesn't seem to actually ever occur
            print("Warning (9): tid = {}, pid = {}, edit_years = {}, edit_months = {}, edit_days = {}".format(tid, pid, edit_years, edit_months, edit_days))
          post_info["edit_year"] = str(int(df_edit.iloc[-1]["edit_year"]))
          post_info["edit_month"] = str(int(df_edit.iloc[-1]["edit_month"]))
          post_info["edit_day"] = str(int(df_edit.iloc[-1]["edit_day"]))
        if len(edit_times) == 1:
          post_info["edit_time"] = edit_times[0]
        else: # Note, since edit times are never missing (NaN), we can take the value of the bottom row as the 'last' value
          if len(edit_times) < 1: 
            print("Warning (10): tid = {}, pid = {}, times = {}".format(tid, pid, edit_times))
          post_info["edit_time"] = df_edit.iloc[-1]["edit_time"]

      # Identify all gaps! (Note: relies on higher pid's being generated later, thus by going through them in an ascended sorting we can observe gaps based on sequence_id's)
      seqs = [x for x in df["seq_id"].unique() if str(x) != "nan"]
      max_seq = max(seqs)
      if max_seq > prev_seq + 1:
        print("Gap at tid={}, pid={}. Gap size of {}".format(tid, pid, max_seq-prev_seq-1))
        gaps_found += 1
        gap_cumulative_size_found += max_seq-prev_seq-1
        gap_tids.add(tid)
      prev_seq = max_seq

      # Determine if an error occurred at any time, and then check if they were not already resolved with our choices above
      errors = [x for x in df["error"].unique() if x==x]
      if len(errors) == 1:
        post_info["error"] = errors[0]
      elif len(errors) > 1:
        post_info["error"] = min(errors)  # if multiple remember most 'significant' error

      # Store post info
      post_collection.append(post_info)

    # resolve seq_id's skipping over gaps and ignoring posts being deleted
    topic_posts = pd.DataFrame(post_collection).sort_values(["year", "month", "day", "time"], ascending=[True, True, True, True]).reset_index(drop=True)
    for i in range(len(topic_posts)):
      topic_posts.at[i, "seq_id"] = i + 1
    # store topic
    topic_collection.append(topic_posts)

  print("{} Gaps found in {} topics, with cumulative size {}.\nIn topics {}".format(gaps_found, len(gap_tids), gap_cumulative_size_found, gap_tids))

  # Store and return a dataframe with the resolved forum post data. The error information is dropped for the final dataset
  # Additionally, username information is dropped as this can be retrieved through the uid from the user information
  df_posts_static = pd.concat(topic_collection).drop(columns=["username", "edit_username", "error"])
  df_posts_static.to_csv(os.path.join(args["outdir"], "forum", posts_file), sep='\t', float_format="%.0f", index=False)
  return df_posts_static

#############################################################################################
# Functions for preprocessing data on users
#############################################################################################

def resolveUsernameConflicts(dfus, var):
  '''Checks if there are multiple usernames, and if so, resolves known and outputs unknown cases
  Parameters:
    dfus  - list of pandas dataframes from which records should be checked
    var   - string of column name to check (likely always "username")
  Returns:
    the unique or resolved username
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x}
  if len(var_set) > 1:
    if "LinQue" in var_set:
      return "LinQue"
    elif "only" in var_set:
      return "only"
    elif "lot_oo7" in var_set:
      return "lot_oo7"
    elif "Luxor" in var_set:
      return "Luxor"
    elif "Ozzyz" in var_set:
      return "Ozzyz"
    else:
      print("Error (u1): multiple {}s detected for uid {}. Options are: {}".format(var, dfus[0]["uid"], var_set))
  elif len(var_set) == 1:
    return list(var_set)[0]
  else:
    return None

def resolveUserInfoConflicts(dfus, info, var):
  ''' Determines whether there are any conflicts for a given variable and (if known) resolves them
  Parameters:
    dfus  - List of panda dataframes within which the variable must be checked for conflicts
    info  - Dictionary in which the resolved variable must be stored
    var   - Variable (string) for which conflicts must be checked
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x}
  if len(var_set) > 1:
    if var == "num_posts":
      info[var] = max(var_set)
    elif var == "title":
      info[var] = getMaxTitle(var_set)
    else:
      print("Error (2): multiple {}s detected for uid {}. Options are: {}".format(var, info["uid"], var_set))
  elif len(var_set) != 0:
    info[var] = list(var_set)[0]

def checkResolvedUserErrors(info):
  '''Check if error information stored was not already resolved by information pulled from different extracted sources
  Parameters:
    info - a dictionary storing information on the current user under consideration
  '''
  if info["error"]:
    if info["username"] and info["reg_year"] and info["reg_month"] and info["reg_day"] and info["title"]: # Minimum info is there
      # Check whether there are 0 posts and thus no last post information expected, or if expected whether it has been found
      if info["num_posts"] == 0 or (info["lp_year"] and info["lp_month"] and info["lp_day"] and info["lp_time"] and info["num_posts"]):
        # If all relevant information (excluding the optional 'location') is included, we remove the error!
        info["error"] = None


def fillOutUserData(args, df_prof, df_uid, df_posts, tf_usernames, scrape_ids):
  '''Combine and resolve conflicts for forum user information that was extracted
  Parameters:
    args         - dictionary of command line arguments given
    df_prof      - a dataframe containing forum user profile information that was extracted
    df_uid       - a dataframe containing all username, uid combinations found among the various types of extracted data
    df_posts     - a dataframe containing forum user information extracted from posts
    tf_usernames - a list of all usernames that were found to have posted a first or last post in the extracted data
                   (possibly without existing matching uid, requiring a new uid to be defined for them)
    scrape_ids   - list of all scrape identifiers
  Returns: a dataframe with the combined and resolved forum user information
  '''
  df_forum_topic = pd.read_csv(os.path.join(args["indir"], fora_topic_file), sep="\t", usecols=["first_user", "first_uid", "scrape_id", "lp_user", "lp_uid"])

  uids = list(df_prof["uid"].unique())
  for uid in df_uid["uid"].unique():
    if uid not in uids:
      uids.append(uid)
  for uid in df_posts["uid"].unique(): # Note, this should not provide new uid's anymore as they were already included in df_uid earlier, however, this checks just to be sure
    if uid not in uids:
      uids.append(uid)
  uids = [uid for uid in uids if uid == uid] # Try and exclude nan

  users = []
  for uid in sorted(uids):
    print("Now processing uid {}  ".format(uid), end="\r")
    dfu_prof  = df_prof.loc[df_prof["uid"] == uid]
    dfu_uid   = df_uid.loc[df_uid["uid"] == uid]
    dfu_posts = df_posts.loc[df_posts["uid"] == uid]

    # Determine if we are dealing with a uid for which we simply don't have any other information, and create a single instance for it for each relevant scrape (such that we can have a unified uid for topic and post processing later!)
    if len(dfu_prof) == 0 and len(dfu_posts) == 0:
      dfu_for_first = df_forum_topic.loc[df_forum_topic["first_uid"] == uid][["first_user", "scrape_id"]]
      dfu_for_first.columns = ["username", "scrape_id"]
      dfu_for_last = df_forum_topic.loc[df_forum_topic["lp_uid"] == uid][["lp_user", "scrape_id"]]
      dfu_for_last.columns = ["username", "scrape_id"]

      usn = resolveUsernameConflicts([dfu_for_first, dfu_for_last], "username")
      relevant_scrapes = set(dfu_for_first["scrape_id"].unique()).union(set(dfu_for_last["scrape_id"].unique()))
      for sid in sorted(list(relevant_scrapes)):
        user_info = {"uid":uid, "username":usn,
                     "reg_year":None, "reg_month":None, "reg_day":None,
                     "scrape_id":sid, "title":None,
                     "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                     "num_posts":None, "location":None, "error":None}
        users.append(user_info)
      continue

    # Determine username and conflicts if they exist
    usn = resolveUsernameConflicts([dfu_prof, dfu_uid, dfu_posts], "username")
    reg_date = resolveDateConflict([dfu_prof, dfu_posts], {"year":"reg_year", "month":"reg_month", "day":"reg_day"}, "uid {}".format(uid))

    # For each scrape extract scrape dependent information
    for sid in sorted(scrape_ids):
      user_info = {"uid":uid, "username":usn,
                   "reg_year":reg_date.year, "reg_month":reg_date.month, "reg_day":reg_date.day,
                   "scrape_id":sid, "title":None,
                   "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                   "num_posts":None, "location":None, "error":None}

      dfus_prof  = dfu_prof.loc[dfu_prof["scrape_id"] == sid]
      dfus_posts = dfu_posts.loc[dfu_posts["scrape_id"] == sid]

      resolveUserInfoConflicts([dfus_prof, dfus_posts], user_info, "title")
      if user_info["title"] is None: # skip unnecessary work, no information exists for this user this scrape! (also prevents username is nan)
        continue
      resolveUserInfoConflicts([dfus_prof], user_info, "lp_year")
      resolveUserInfoConflicts([dfus_prof], user_info, "lp_month")
      resolveUserInfoConflicts([dfus_prof], user_info, "lp_day")
      resolveUserInfoConflicts([dfus_prof], user_info, "lp_time")
      resolveUserInfoConflicts([dfus_prof, dfus_posts], user_info, "num_posts")
      resolveUserInfoConflicts([dfus_prof], user_info, "location")
      resolveUserInfoConflicts([dfus_prof], user_info, "error")
      checkResolvedUserErrors(user_info)
      users.append(user_info)

  df_users_temp = pd.DataFrame(users)
  # Next we make sure that users for whom we never captured the uid but do have username and other information get included with a 'new' uid
  usernames = list(df_prof["username"].unique())
  for usn in df_uid["username"].unique():
    if usn not in usernames:
      usernames.append(usn)
  for usn in df_posts["username"].unique():
    if usn not in usernames:
      usernames.append(usn)
  for usn in df_posts["edit_username"].unique():
    if usn not in usernames:
      usernames.append(usn)
  for usn in tf_usernames:
    if usn not in usernames:
      usernames.append(usn)

  ignore_names = set(df_users_temp["username"].unique())
  ignore_names.update(["dredknotz", "only_bak", "loste", "ShadyTom", "ozzyz"])
  max_uid = max(df_users_temp["uid"].unique())
  for usn in usernames:
    if usn not in ignore_names and usn==usn: # create new user
      print("Now processing username {}                    ".format(usn), end="\r")
      dfu_prof  = df_prof.loc[df_prof["username"] == usn]
      #dfu_uid   = df_uid.loc[df_uid["username"] == usn]
      dfu_posts = df_posts.loc[df_posts["username"] == usn]
      max_uid += 1

      # Determine if we are dealing with a username for which we simply don't have any other information, and create a single instance for it for each relevant scrape (such that we can have a unified uid for topic and post processing later!)
      if len(dfu_prof) == 0 and len(dfu_posts) == 0:
        dfu_edit_posts = df_posts.loc[df_posts["edit_username"] == usn]
        dfu_for_first = df_forum_topic.loc[df_forum_topic["first_user"] == usn]
        dfu_for_last = df_forum_topic.loc[df_forum_topic["lp_user"] == usn]

        relevant_scrapes = set(dfu_edit_posts["scrape_id"].unique()).union(set(dfu_for_first["scrape_id"].unique())).union(set(dfu_for_last["scrape_id"].unique()))
        for sid in sorted(list(relevant_scrapes)):
          user_info = {"uid":max_uid, "username":usn,
                       "reg_year":None, "reg_month":None, "reg_day":None,
                       "scrape_id":sid, "title":None,
                       "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                       "num_posts":None, "location":None, "error":None}
          users.append(user_info)
        continue

      # If there is more information available, resolve it
      reg_date = resolveDateConflict([dfu_prof, dfu_posts], {"year":"reg_year", "month":"reg_month", "day":"reg_day"}, "username {}".format(usn))

      # For each scrape extract scrape dependent information
      for sid in sorted(scrape_ids):
        user_info = {"uid":max_uid, "username":usn,
                     "reg_year":reg_date.year, "reg_month":reg_date.month, "reg_day":reg_date.day,
                     "scrape_id":sid, "title":None,
                     "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                     "num_posts":None, "location":None, "error":None}
        
        dfus_prof  = dfu_prof.loc[dfu_prof["scrape_id"] == sid]
        dfus_posts = dfu_posts.loc[dfu_posts["scrape_id"] == sid]

        resolveUserInfoConflicts([dfus_prof, dfus_posts], user_info, "title")
        if user_info["title"] is None: # skip all them unnecessary work!
          continue
        resolveUserInfoConflicts([dfus_prof], user_info, "lp_year")
        resolveUserInfoConflicts([dfus_prof], user_info, "lp_month")
        resolveUserInfoConflicts([dfus_prof], user_info, "lp_day")
        resolveUserInfoConflicts([dfus_prof], user_info, "lp_time")
        resolveUserInfoConflicts([dfus_prof, dfus_posts], user_info, "num_posts")
        resolveUserInfoConflicts([dfus_prof], user_info, "location")
        resolveUserInfoConflicts([dfus_prof], user_info, "error")
        checkResolvedUserErrors(user_info)
        users.append(user_info)

  # Store and return a dataframe with the resolved forum user data. The error information is dropped for the final dataset
  df_users = pd.DataFrame(users).drop(columns="error")
  df_users.to_csv(os.path.join(args["outdir"], "forum", profile_file), sep='\t', float_format="%.0f", index=False)
  return df_users

def getPostUserDataDataframe():
  '''Retrieves user information from all post data for each scrape and combines it into one dataframe
  Returns:
    - a dataframe of all user information obtained from post data
    - list of all scrape identifiers
  '''
  df_scrape = pd.read_csv(os.path.join(args["indir"], scrapes_file), sep="\t", index_col=0)
  # Gather user data from all posts
  scrape_dfs = []
  for scrape_id in df_scrape.index:
    scrape_post_file = os.path.join(args["indir"], posts_file[:-4] + "-scrape-" + str(scrape_id) + ".tsv")
    scrape_dfs.append(pd.read_csv(scrape_post_file, sep='\t', usecols=["pid", "uid", "username", "user_title", "reg_year", "reg_month", "reg_day", "user_posts", "scrape_id", "edit_username"]).drop_duplicates().reset_index(drop=True))
  #print(scrape_dfs)
  # Merge into one dataframe without duplicates
  df_posts = scrape_dfs[0]
  for i in range(1,len(scrape_dfs)):
    df_posts = pd.concat([df_posts, scrape_dfs[i]], ignore_index=True)#.drop_duplicates()
    #df_posts = df_posts.append(scrape_dfs[i], ignore_index=True)
  return df_posts.drop_duplicates().sort_values(["uid"], ascending=[True]).reset_index(drop=True), list(df_scrape.index)


def preprocessUserData(args):
  '''Retrieve all user information from extracted data, combine it and resolve data quality issues for it.
  Parameters:
    args - dictionary of command line arguments given
  Returns: a dataframe with the combined and resolved forum user information
  '''

  ## First we retrieve what user data we can from non-profile files
  # Retrieve forum topic first and last post users usernames and uid's
  df_tf_first = pd.read_csv(os.path.join(args["indir"], fora_topic_file), sep="\t", usecols=["first_user", "first_uid"])[["first_uid", "first_user"]].drop_duplicates().sort_values(["first_uid"], ascending=[True]).reset_index(drop=True)
  df_tf_first.columns = ["uid", "username"]
  df_tf_last = pd.read_csv(os.path.join(args["indir"], fora_topic_file), sep="\t", usecols=["lp_user", "lp_uid"])[["lp_uid", "lp_user"]].drop_duplicates().sort_values(["lp_uid"], ascending=[True]).reset_index(drop=True)
  df_tf_last.columns = ["uid", "username"]
  # Combine first and last post username and uid data
  df_tf_full = pd.concat([df_tf_first, df_tf_last], ignore_index=True).drop_duplicates()
  df_tf = df_tf_full.dropna().sort_values(["uid"], ascending=[True]).reset_index(drop=True)
  # Determine the set of usernames involved in first/last posts regardless of known associated uid, such that we can assign one if necessary
  tf_usernames = df_tf_full["username"].unique()
  # Retrieve uid, username information from posts
  df_posts, scrape_ids = getPostUserDataDataframe()
  df_posts.columns = ["pid", "uid", "username", "title", "reg_year", "reg_month", "reg_day", "num_posts", "scrape_id", "edit_username"]
  df_post_users = df_posts[["uid", "username"]].dropna().drop_duplicates().sort_values(["uid"], ascending=True).reset_index(drop=True)
  # Combine post and first/last post information
  df_temp = pd.concat([df_tf, df_post_users], ignore_index=True).drop_duplicates().sort_values(["uid"], ascending=[True]).reset_index(drop=True)
  # Retrieve user profile information
  df_profiles = pd.read_csv(os.path.join(args["indir"], profile_file), sep="\t", index_col=False)
  df_profiles.columns = ["uid", "username", "reg_year", "reg_month", "reg_day", "scrape_id", "title", "lp_year", "lp_month", "lp_day", "lp_time", "num_posts", "location", "error"]
  df_profiles_users = df_profiles[["uid", "username"]].dropna().drop_duplicates().sort_values(["uid"], ascending=True).reset_index(drop=True)
  # Combine all sources of uid, username information into a single dataframe
  df_uid = pd.concat([df_temp, df_profiles_users], ignore_index=True).drop_duplicates().sort_values(["uid"], ascending=[True]).reset_index(drop=True)

  return fillOutUserData(args, df_profiles, df_uid, df_posts, tf_usernames, scrape_ids)

#############################################################################################
# Main functions
#############################################################################################

def preprocessForumData(args):
  '''Preprocess all forum data one type of data at a time, in such an order that one type of data can rely
     on a previously resolved data type when needed. Resolved data is stored in specified output directory.
  Parameters:
    args - dictionary of command line arguments given (specifying input and output directories)
  '''
  # First we preprocess the scrapes.tsv file, though this is a simply copy to target directory
  df_scrape = preprocessScrapeData(args)
  # Second we preprocess user data, as having this as complete as possible will be useful for post and topic preprocessing
  df_users = preprocessUserData(args)
  # Third we preprocess the data at the post level, the most relevant level of the bunch
  df_posts = preprocessPostData(args, df_users)
  # Fourth we preprocess the next level mode, i.e., topic data
  df_topics = preprocessTopicData(args, df_scrape, df_users, df_posts)
  # Lastly we preprocess the most high level mode, i.e., forum data
  preprocessForaData(args, df_scrape, df_posts, df_topics)

if __name__ == "__main__":
  sys.stdout = Logger()
  start_time = timeit.default_timer()

  # Process command line input to obtain input and output base directories
  input_parser = InputParser()
  args = input_parser.getInputArgumentsAsDict()
  os.makedirs(os.path.join(args["outdir"], "forum"), exist_ok=True)

  # Preprocess forum data
  preprocessForumData(args)

  stop_time = timeit.default_timer()
  print("Total runtime: {}s".format(stop_time - start_time))

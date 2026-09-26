import numpy as np
import pandas as pd
import timeit

import re

import argparse
import sys
import os
import datetime as dt

#############################################################################################
# set some global variables
#############################################################################################

# Input forum and market directories (relative to base directory)
indir_forum = "evolution-forums"
indir_market = "evolution"

# output information splitters
info_splitter = "\t-----------------------"
scrape_splitter = "================================="

# Forum file prefixes
index_file_prefix = "index."
profile_file_prefix = "profile.php?id="
topic_file_prefix = "viewtopic.php?id="
topic_alt_file_prefix = "viewtopic.php?pid="
forum_file_prefix = "viewforum.php?id="

# Extracted forum data output files (relative to base output directory)
scrapes_output_file_forum  = "extracted-unrefined/scrapes.tsv"
profile_output_file     = "extracted-unrefined/user.tsv"
topics_output_file      = "extracted-unrefined/topic.tsv"
posts_output_file       = "extracted-unrefined/post.tsv"
quotes_output_file      = "extracted-unrefined/quote.tsv"
fora_output_file        = "extracted-unrefined/forum.tsv"
fora_topic_output_file  = "extracted-unrefined/forum-topic.tsv"

index_fora_output_file  = "extracted-unrefined/index-forum.tsv"
glob_stats_output_file  = "extracted-unrefined/global-stats.tsv"

# Extracted market data output files (relative to base output directory)
scrapes_output_file_market = "extracted-unrefined/market-scrapes.tsv"
listings_output_file       = "extracted-unrefined/market-listings.tsv"
feedback_listings_output_file = "extracted-unrefined/market-feedback-listings.tsv"
feedback_output_file       = "extracted-unrefined/market-feedback.tsv"
rp_listings_output_file    = "extracted-unrefined/market-rp-listings.tsv"
profiles_output_file       = "extracted-unrefined/market-profiles.tsv"
categories_output_file        = "extracted-unrefined/market-categories.tsv"
category_listings_output_file = "extracted-unrefined/market-category-listings.tsv"
store_listings_output_file    = "extracted-unrefined/market-store-listings.tsv"

# Vendor rank ordering used up to market scrape 13
early_rank_order = {"Freshman": 1, "Sophomore": 2, "Junior": 3, "Senior": 4, "Premium": 5,
                    "Advanced": 6, "Expert": 7, "Master": 8, "Grandmaster": 9, "Godlike": 10}

#############################################################################################
# Logger functions
#############################################################################################

class Logger(object):
  def __init__(self):
    self.terminal = sys.stdout
    self.log = open("logfile-extract.log", "w")

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
    self.parser = argparse.ArgumentParser(description="Extracts forum and market information from raw source files, location of which must be specified, and stores them in specified output base directory locations.")
    self.setArguments()
    self.printInput()

  def setArguments(self):
    self.parser.add_argument('-in', "--indir", required=True, help="Location of raw source base directory with expected subdirectories evolution-forums and evolution")
    self.parser.add_argument('-out', "--outdir", required=True, help="Location of base directory where extracted data is to be stored (to then be used as input for subsequent preprocessing")

  def getInputArgumentsAsDict(self):
    return vars(self.parser.parse_args())

  def printInput(self):
    args = self.getInputArgumentsAsDict()
    print(scrape_splitter)
    for label in args.keys():
      print("{}: {}".format(self.parser._option_string_actions["--" +label].help, args[label]))
    print(scrape_splitter + "\n")

#############################################################################################
# Help functions
#############################################################################################

def getDate(date_raw, file):
  """Converts raw date into year, month and day (including Yesterday and Today input)
  Parameters:
    date_raw - Raw date to convert
    file     - file path to obtain scrape date from (in case of Yesterday/Today)
  Returns: year, month and day described by date_raw
  """
  if date_raw == "Yesterday":
    yesterday = dt.datetime.fromtimestamp(os.path.getmtime(file)) -  dt.timedelta(days=1)
    year = yesterday.year
    month = yesterday.month
    day = yesterday.day
  elif date_raw == "Today":
    today = dt.datetime.fromtimestamp(os.path.getmtime(file))
    year = today.year
    month = today.month
    day = today.day
  else:
    reg = date_raw.split("-")
    year = int(reg[0])
    month = int(reg[1])
    day = int(reg[2])
  return year, month, day

def getDateSimple(date_raw):
  """Converts raw date into year, month and day
  Parameters:
    date_raw - Raw date to convert
  Returns: year, month and day described by date_raw
  """
  reg = date_raw.split("-")
  year = int(reg[0])
  month = int(reg[1])
  day = int(reg[2])
  return year, month, day

def setForumWarning(info, wid, text, file):
  """Outputs a warning and sets the error variable info["error"]"""
  file_split = file.split("/")
  print("Warning ({}): {} {}".format(wid, text, os.path.join(file_split[-2], file_split[-1])))
  if info["error"] is None:
    info["error"] = wid

def setMarketWarning(info, wid, text, file):
  """Outputs a warning and sets the error variable info["error"]"""
  print("Warning ({}): {} {}".format(wid, text, file.split("evolution/")[-1]))
  if info["error"] is None: # We don't want to overwrite a lower value, i.e., higher class, errors!
    info["error"] = wid

#############################################################################################
# Scrape extraction functions
#############################################################################################

def generateScrapeIDs(indir, outfile):
  """Generates a temporally ordered id for each scrape and stores the id and date of scrape
  Parameters:
    indir   - path to directory listing all scrape directories
    outfile - file to output determines scrape_id's and date information into
  Returns:
    scrapes - dictionary of elements (directory name of scrape):scrape_id
  """
  directory_contents = os.listdir(os.path.abspath(indir))
  scrapes = {}
  with open(outfile, 'w') as f:
    f.write("scrape_id\tscrape_year\tscrape_month\tscrape_day\n")
    for i in range(len(directory_contents)):
      date = directory_contents[i]
      scrapes[date] = i
      if date[-1] == 'v':
        date = date[:-1]
      year, month, day = getDateSimple(date)
      f.write("{}\t{}\t{}\t{}\n".format(i, year, month, day))
  return scrapes

#############################################################################################
# Profile extraction functions
#############################################################################################

def extractProfile(file, info):
  """Extracts various pieces of information from a single profile file from a scrape
  Parameters:
    file  - path to the file from which information should be extracted
    info  - dictionary in which the extracted profile information is to be stored
  Post:
    info dictionary is filled with all available information on the user in file
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setForumWarning(info, 0, "Empty profile file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<h2>An error was encountered</h2>", fc)) > 0:
      setForumWarning(info, 1, "An error occurred while scraping profile file", file)
      return
    # Check if we are looking at the scrapers profile, if so 'ignore' it as it seems that the scrapers never post, so there is no value in adding them in the dataset!
    if re.findall(r"<p>Username: \w+</p>", fc):
      setForumWarning(info, 2, "Scraper\'s profile found. Entry deleted as scraper's never post! (uid = {})".format(info["uid"]), file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body></html>", fc)) == 0:
      setForumWarning(info, 3, "Partial profile file", file)

    # Get guaranteed profile elements
    usernames = re.findall(r"(?<=<dt>Username</dt><dd>)[^<]+", fc)
    if len(usernames) == 0:
      usernames = re.findall(r"(?<=<dt>Username</dt><dd><span class=\"gid\d\">)[^<]+", fc)
      if len(usernames) == 0:
        usernames = re.findall(r"(?<=<dt>Username</dt><dd><span class=\"gid\d\d\">)[^<]+", fc)
    registration = re.findall(r"(?<=<dt>Registered</dt><dd>)[^<]+", fc)
    titles = re.findall(r"(?<=<dt>Title</dt><dd>)[^<]+", fc)
    posts = re.findall(r"(?<=<dt>Posts</dt><dd>)[\d,]+", fc)

    # Check for irregularities
    if len(usernames) != 1:
      setForumWarning(info, 10, "Missing (or too many) usernames in profile file", file)
    else: # Update profile information if no irregularities were detected
      info["username"] = usernames[0]
    if len(registration) != 1:
      setForumWarning(info, 11, "Missing (or too many) registrations in profile file", file)
    else: # Update profile information if no irregularities were detected
      info["reg_year"], info["reg_month"], info["reg_day"] = getDate(registration[0], file)
    if len(titles) != 1:
      setForumWarning(info, 12, "Missing (or too many) titles in profile file", file)
    else: # Update profile information if no irregularities were detected
      info["title"] = titles[0]
    if len(posts) != 1:
      setForumWarning(info, 13, "Missing (or too many) post counts in profile file", file)
    else: # Update profile information if no irregularities were detected
      info["posts"] = int(posts[0].replace(",",""))


    # Get optional last post information (always present if #posts > 0)
    if info["posts"] > 0:
      last_posts = re.findall(r"(?<=<dt>Last post</dt><dd>)[^<]+", fc)
      # Check for irregularities
      if len(last_posts) != 1:
        setForumWarning(info, 14, "Missing (or too many) last post information in profile file", file)
      else: # Update profile information if no irregularities were detected
        lp_datetime = last_posts[0].split(' ')
        info["lp_year"], info["lp_month"], info["lp_day"] = getDate(lp_datetime[0], file)
        info["lp_time"] = lp_datetime[1]

    # Get optional location information
    locations = re.findall(r"(?<=<dt>Location</dt><dd>)[^<]+", fc)
    # Check for irregularities
    if len(locations) > 1:
      setForumWarning(info, 15, "Too many locations found in profile file", file)
    elif len(locations) == 1: # Update profile information if no irregularities detected
      info["location"] = locations[0]

def extractProfiles(scrape_id, scrape_path, files):
  """This function extracts all profiles of a single scrape
  Parameters:
    scrape_id   - id of scrape to extract from
    scrape_path - path to directory containing scrape files
    files       - filenames of all profiles in the scrape
  Returns:
    profiles        - a list of dictionaries containing user profile information
    faulty_profiles - a list of file descriptors of files that are faulty/incomplete
  """
  profiles = []
  faulty_profiles = []
  for file in files:
    uid = file[len(profile_file_prefix):]
    info = {"uid":int(uid), "username":'', "reg_year":None, "reg_month":None, "reg_day":None,
            "scrape_id":scrape_id, "title":'', "lp_year":None, "lp_month":None, "lp_day":None,
            "lp_time":None, "posts":0, "location":None, "error":None}
    extractProfile(os.path.join(scrape_path, file), info)
    if info["error"] is not None: # Remember which files contained errors, for possible later analysis
      faulty_profiles.append(os.path.join(scrape_path.split("/")[1],file))
    if info["error"] not in (0,1,2): # For these error types there is no relevant information to store
      profiles.append(info)
  return profiles, faulty_profiles

#############################################################################################
# Topic extraction functions
#############################################################################################

def extractPostSignature(postmsg, post_info, file):
  """Extracts post signature information from the post text.
  Parameters:
    postmsg     - string of raw source containing the post text (as stored as such)
    post_info   - a dictionary storing information on this post in the given scrape/topic
    file        - path to the file from which the 'postmsg' string was obtained
  Returns:
    postmsg - post message string with signature removed if it was present
  """
  signature_raw = re.findall(r"(?<=<div class=\"postsignature postmsg\"><hr />).*?(?=</div></div></div></div>)", postmsg)
  signature_check = re.findall(r"(?<=<div class=\"postsignature postmsg\"><hr />).*", postmsg)

  if len(signature_raw) == 1 and len(signature_check) == 1:
    post_info["signature"] = signature_raw[0]
    return re.findall(r".*?(?=</div><div class=\"postsignature postmsg\"><hr />)", postmsg)[0]
  else:
    if len(signature_raw) > 1:
      setForumWarning(post_info, 51, "Too many post signatures in topic page file", file)
    if len(signature_raw) == 1:
      setForumWarning(post_info, 52, "Unexpected end to post signature causing miss in topic page file", file)
    return postmsg

def extractPostEditInformation(postmsg, post_info, file):
  """Extracts post edit information from the post text.
  Parameters:
    postmsg     - string of raw source containing the post text (as stored as such)
    post_info   - a dictionary storing information on this post in the given scrape/topic
    file        - path to the file from which the 'postmsg' string was obtained
  Returns:
    postmsg - post message string with edit information removed if it was present
  """
  edit_raw = re.findall(r"(?<=<p class=\"postedit\"><em>).*?(?=</em></p>)", postmsg)
  if len(edit_raw) == 1:
    edit_username = re.findall(r"(?<=Last edited by ).*?(?= \()", edit_raw[0])
    edit_datetime_raw = re.findall(r"(?<=\().*?(?=\))", edit_raw[0])
    if len(edit_datetime_raw) != 1 or len(edit_username) !=  1:
      setForumWarning(post_info, 54, "Irregularity in edit information in topic page file", file)
    else:
      post_info["edit_username"] = edit_username[0]
      edit_datetime = edit_datetime_raw[0].split(' ')
      post_info["edit_year"], post_info["edit_month"], post_info["edit_day"] = getDate(edit_datetime[0], file)
      post_info["edit_time"] = edit_datetime[1]
    return re.findall(r".*?(?=<p class=\"postedit\"><em>)", postmsg)[0]
  elif len(edit_raw) > 1:
    setForumWarning(post_info, 53, "Multiple instance of postedit class in topic page file", file)
  return postmsg

def extractQuotes(postmsg, quotes, post_info, file):
  """Extracts quotes from the post text.
  Parameters:
    postmsg     - string of raw source containing the post text (as stored as such)
    quotes      - a list of dictionaries each storing information on a quote in this scrape/topic
    post_info   - a dictionary storing information on this post in the given scrape/topic
    file        - path to the file from which the 'postmsg' string was obtained
  """
  q_start = re.compile(r"<div class=\"quotebox\">")
  q_end = re.compile(r"</div></blockquote></div>")
  # Check whether there are any quotes
  match = q_start.search(postmsg)
  if match is None: # If there are no quotes
    return None

  # Determine start and end points for quotes
  start_matches = re.finditer(q_start, postmsg)
  end_matches = re.finditer(q_end, postmsg)
  s_pos = []
  e_pos = []
  for sm in start_matches:
    s_pos.append(sm.start())
  for em in end_matches:
    e_pos.append(em.end())
  if len(s_pos) != len(e_pos):
    setForumWarning(post_info, 50, "Unequal number of quote starts and endings in topic page file", file)

  # Extract each individual quote (which may contain other quotes within)
  quote_texts = []
  for sp in reversed(s_pos):
    for ep in e_pos:
      if ep > sp:
        quote_texts.insert(0, postmsg[sp:ep])
        e_pos.remove(ep)
        break

  for quote_text in quote_texts:
    # Extract username of user that is quoted (if missing set to None)
    q_users = re.findall(r"(?<=<cite>).*?(?= wrote:</cite>)", quote_text)
    q_user = None
    if len(q_users) > 0:
      q_user = q_users[0]
    # Extract quote text
    q_text = quote_text[re.search(r"<blockquote><div>", quote_text).end():-25]
    # Store extracted information on quote
    quote = {"scrape_id":post_info["scrape_id"], "pid":post_info["pid"],
             "quote_username":q_user, "quote_text":q_text,
             "quote_uid":None, "quote_pid":None} # These two can not be directly obtained
    quotes.append(quote)

def extractPost(file, post_raw, post_info, quotes):
  """Extracts post information from 'post_raw' and stores it in the post_info dictionary.
  Possible quotes are extracted and appended to the list of quote dictionaries in 'quotes'.
  Parameters:
    file      - path to the file from which the 'post_raw' string was obtained
    post_raw  - string containing the raw source covering all information on a single post as obtained from a topic page file
    post_info - a dictionary storing information on this post in the given scrape/topic
    quotes    - a list of dictionaries each storing information on a quote in this scrape/topic
  """

  # Extract (supposedly) guaranteed post information
  post_info["pid"] = int(re.findall(r"(?<=viewtopic\.php\?pid=)\d+", post_raw)[0])
  post_date, post_info["time"] = re.findall(r"(?<=viewtopic\.php\?pid="+str(post_info["pid"])+"#p"+
                                            str(post_info["pid"])+r"\">)[^<]+", post_raw)[0].split(' ')
  post_info["year"], post_info["month"], post_info["day"] = getDate(post_date, file)

  post_info["seq_id"] = int(re.findall(r"(?<=class=\"conr\">#)\d+", post_raw)[0])

  uid = re.findall(r"(?<=href=\"profile\.php\?id=)\d+", post_raw)
  if len(uid) == 0:
    usernames = re.findall(r"(?<=<div class=\"postleft\"><dl><dt><strong><span class=\"gid\d\">)[^<]+", post_raw)
    if len(usernames) == 0:
      usernames = re.findall(r"(?<=<div class=\"postleft\"><dl><dt><strong><span class=\"gid\d\d\">)[^<]+", post_raw)
  else:
    post_info["uid"] = int(uid[0])
    usernames = re.findall(r"(?<=href=\"profile\.php\?id="+str(post_info["uid"])+r"\">)[^<]+", post_raw)
    if len(usernames) == 0:
      usernames = re.findall(r"(?<=href=\"profile\.php\?id="+str(post_info["uid"])+r"\"><span class=\"gid\d\">)[^<]+", post_raw)
      if len(usernames) == 0:
        usernames = re.findall(r"(?<=href=\"profile\.php\?id="+str(post_info["uid"])+r"\"><span class=\"gid\d\d\">)[^<]+", post_raw)
  post_info["username"] = usernames[0]

  post_info["user_title"] = re.findall(r"(?<=class=\"usertitle\"><strong>)[^<]+", post_raw)[0]
  if post_info["user_title"] != "Guest":
    reg_date = re.findall(r"(?<=<span>Registered: )[^<]+", post_raw)[0]
    post_info["reg_year"], post_info["reg_month"], post_info["reg_day"] = getDate(reg_date, file)
    post_info["user_posts"] = int((re.findall(r"(?<=<span>Posts: )[\d,]+", post_raw)[0]).replace(',',''))

  # Extract post message and quotes (if present)
  postmsg = re.findall(r"(?<=class=\"postmsg\">).+?(?=<div class=\"inbox\">)", post_raw)[0]
  postmsg = extractPostSignature(postmsg, post_info, file)
  postmsg = extractPostEditInformation(postmsg, post_info, file)
  post_info["text"] = postmsg
  extractQuotes(postmsg, quotes, post_info, file)

def extractTopicPage(file, info, posts, all_pids, quotes):
  """Extracts various pieces of information from a single topic (page) file from a scrape
  Parameters:
    file      - path to the file from which information should be extracted
    info      - a dictionary storing information on the topic covered by this file, to update
    posts     - a list of dictionaries each storing information on a post in this scrape/topic
    all_pids  - a list of all post identifiers already found so far
    quotes    - a list of dictionaries each storing information on a quote in this scrape/topic
  Returns:
    num_posts - number of posts extracted from topic page
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setForumWarning(info, 0, "Empty topic file", file)
      return 0
    # Check if an error was encountered
    if len(re.findall(r"<h2>An error was encountered</h2>", fc)) > 0:
      setForumWarning(info, 1, "An error occurred while scraping topic file", file)
      return 0
    # Check if only part of the file is available
    if len(re.findall(r"</body></html>", fc)) == 0:
      setForumWarning(info, 3, "Partial topic file", file)

    # Update topic information with topic title and forum id
    titles = re.findall(r"(?<=<title>).*?(?= \(Page)", fc)
    if len(titles) != 1:
      setForumWarning(info, 20, "Title irregularity in topic file", file)
    elif info["title"] is None:
      info["title"] = titles[0]
    elif info["title"] != titles[0]:
      setForumWarning(info, 21, "Conflicting topic titles, overwritten with latest found for topic file", file)
      info["title"] = titles[0]

    fids = re.findall(r"(?<=viewforum\.php\?id=)\d+", fc)
    if len(fids) == 0:
      setForumWarning(info, 22, "No forum id found in topic file", file)
    elif info["fid"] is None:
      info["fid"] = int(fids[0])
    elif info["fid"] != int(fids[0]):
      setForumWarning(info, 23, "Conflicting forum ids, overwritten with latest found for topic file", file)
      info["fid"] = int(fids[0])

    # Extract posts and their details from this page
    posts_raw = re.findall(r"blockpost.*?postfootleft", fc)
    num_posts = 0
    for post_raw in posts_raw:
      post_info = {"pid":None, "uid":None, "year":None, "month":None, "day":None, "time":None,
                   # topic-post linkage information
                   "tid":info["tid"], "seq_id":None,
                   # Use this information to supplement and check profile information
                   "username":None, "user_title":None,
                   "reg_year":None, "reg_month":None, "reg_day":None, "user_posts":None,
                   # Scrape specific post information
                   "scrape_id":info["scrape_id"], "text":"", "signature":None, "edit_username":None,
                   "edit_year":None, "edit_month":None, "edit_day":None, "edit_time":None, "error":None}
      extractPost(file, post_raw, post_info, quotes)
      # In practice post extraction encounters no errors (outside of quote structure), thus we may ignore posts already processed previously
      if post_info["pid"] not in all_pids:
        num_posts += 1
        all_pids.append(post_info["pid"])
        posts.append(post_info)
  return num_posts

def extractPIDPage(scrape_id, file, topics, posts, all_pids, quotes):
  """Extracts various pieces of information from a single topic page pid file from a scrape
  Parameters:
    scrape_id - scrape identifier of scrape to which page under consideration belongs
    file      - path to the file from which information should be extracted
    topics    - a list of dictionaries each storing information on a topic in this scrape
    posts     - a list of dictionaries each storing information on a post in this scrape/topic
    all_pids  - a list of all post identifiers already found so far
    quotes    - a list of dictionaries each storing information on a quote in this scrape/topic
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setForumWarning({"error":None}, 0, "Empty pid file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<h2>An error was encountered</h2>", fc)) > 0:
      setForumWarning({"error":None}, 1, "An error occurred while scraping pid file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body></html>", fc)) == 0:
      setForumWarning({"error":None}, 3, "Partial pid file", file)

    # Obtain relevant topic dictionary (or create new one)
    tids = re.findall(r"(?<=<a href=\"viewtopic\.php\?id=)\d+", fc)
    if len(tids) < 1:
      setForumWarning({"error":None}, 5, "Missing topic id in pid file", file)
      return
    tid = int(tids[0])
    info = next((item for item in topics if item["tid"] == tid), None)
    if info is None:
      info = {"tid":tid, "title":None, "retrieval_time":os.path.getmtime(file), "fid":None,
              "scrape_id":scrape_id, "posts":None, "new_posts":None,
              "complete":True, "visible_pre":None, "visible_post":None, "visible":None, "error":None}
      topics.append(info)

    # Update topic information with topic title and forum id
    titles = re.findall(r"(?<=<title>).*?(?= \(Page)", fc)
    if len(titles) != 1:
      setForumWarning(info, 20, "Title irregularity in topic file", file)
    elif info["title"] is None:
      info["title"] = titles[0]
    elif info["title"] != titles[0]:
      # If there is a conflict, we decide on topic title based on the latest information
      extraction_time = os.path.getmtime(file)
      if extraction_time >= info["retrieval_time"]:
        setForumWarning(info, 21, "Conflicting topic titles, overwritten with latest found for pid file", file)
        info["title"] = titles[0]
        info["retrieval_time"] = extraction_time

    fids = re.findall(r"(?<=viewforum\.php\?id=)\d+", fc)
    if len(fids) == 0:
      setForumWarning(info, 22, "No forum id found in topic file", file)
    elif info["fid"] is None:
      info["fid"] = int(fids[0])
    elif info["fid"] != int(fids[0]):
      # If there is a conflict, we decide on forum id based on the latest information
      extraction_time = os.path.getmtime(file)
      if extraction_time >= info["retrieval_time"]:
        setForumWarning(info, 23, "Conflicting forum ids, overwritten with latest found for pid file", file)
        info["fid"] = int(fids[0])
        info["retrieval_time"] = extraction_time

    # Extract posts and their details from this page
    posts_raw = re.findall(r"blockpost.*?postfootleft", fc)
    for post_raw in posts_raw:
      post_info = {"pid":None, "uid":None, "year":None, "month":None, "day":None, "time":None,
                   # topic-post linkage information
                   "tid":info["tid"], "seq_id":None,
                   # Use this information to supplement and check profile information
                   "username":None, "user_title":None,
                   "reg_year":None, "reg_month":None, "reg_day":None, "user_posts":None,
                   # Scrape specific post information
                   "scrape_id":info["scrape_id"], "text":"", "signature":None, "edit_username":None,
                   "edit_year":None, "edit_month":None, "edit_day":None, "edit_time":None, "error":None}
      post_quotes = []
      extractPost(file, post_raw, post_info, post_quotes)
      # In practice post extraction encounters no errors (outside of quote structure), thus we may ignore posts already processed previously
      if post_info["pid"] not in all_pids:
        all_pids.append(post_info["pid"])
        posts.append(post_info)
        for pq in post_quotes:
          quotes.append(pq)

def extractTopic(scrape_path, files, info, posts, all_pids, quotes):
  """ Extracts a single topic (with potentially multiple pages) for a given scrape
  Parameters:
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to topic (page) files covering a single topic in a given scrape
    info        - a dictionary storing all topic variables/information
    posts       - a list of dictionaries each storing information on a post in this scrape
    all_pids    - a list of all post identifiers already found so far
    quotes      - a list of dictionaries each storing information on a quote in this scrape
  Returns:
    faulty_topic_pages  - a list of file descriptors of files that are faulty/incomplete
    num_posts           - number of new posts found among the pages for the topic under consideration
  """
  # Extract posts and other topic related information from files
  faulty_topic_pages = []
  num_posts = 0

  file_extraction_dates = {}
  for file in files:
    file_extraction_dates[file] = os.path.getmtime(os.path.join(scrape_path, file))
  # Iterate over a files in order of extraction datetime
  for file, date in sorted(file_extraction_dates.items(), key=lambda item: item[1]):
    num_posts += extractTopicPage(os.path.join(scrape_path, file), info, posts, all_pids, quotes)
    info["retrieval_time"] = date
  if info["error"] is not None:
    faulty_topic_pages.append(os.path.join(scrape_path.split("/")[1],file))
  return faulty_topic_pages, num_posts

def setPostsCompleteAndVisible(info, new_posts):
  """"Determines the completeness of posts retrieve for a topic.
  Parameters:
    info        - a dictionary storing information on a topic in this scrape/topic
    new_posts   - the list of posts of a topic sorted on sequence id
  """
  info["visible"] = len(new_posts)
  info["posts"] = new_posts[-1]["seq_id"]
  if new_posts[0]["seq_id"] == 1:
    i = 1
    while i < info["visible"] and new_posts[i]["seq_id"] == new_posts[i-1]["seq_id"] + 1:
      i += 1
    if i != info["visible"]:
      info["complete"] = False
      info["visible_pre"] = new_posts[i-1]["seq_id"]

      i -= 1
      j = info["visible"] - 2
      while j > i and new_posts[j]["seq_id"] + 1 == new_posts[j+1]["seq_id"]:
        j -= 1
      info["visible_post"] = info["posts"] - new_posts[j+1]["seq_id"] + 1
  else:
    info["complete"] = False
    info["visible_pre"] = 0
    i = 0
    j = info["visible"] - 2
    while j > i and new_posts[j]["seq_id"] + 1 == new_posts[j+1]["seq_id"]:
      j -= 1
    if i == j:
      info["visible_post"] = info["posts"] - new_posts[j]["seq_id"] + 1
    else:
      info["visible_post"] = info["posts"] - new_posts[j+1]["seq_id"] + 1

def extractTopics(scrape_id, scrape_path, files, files_pid, args):
  """Extracts information on the topics included in a given scrape
     stores posts and quotes info for this scrape and returns topics information
  Parameters:
    scrape_id   - id assigned to scrape pointed to by scrape_path
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to all topic (page) files from a single scrape
    files_pid   - all topic page (pid) files from a single scrape
    args        - dictionary of command line arguments given
  Returns:
    topics                  - a list of dictionaries each storing information on a topic in this scrape
    all_faulty_topic_pages  - a list of file descriptors of topic page files that are faulty/incomplete
  """
  topics = []
  posts = []
  all_pids = []
  quotes = []
  all_faulty_topic_pages = []
  # Sort files into topics (grouping pages together)
  topics_files = {}
  for file in files:
    tid = int(re.findall(r"(?<=viewtopic\.php\?id=)\d+", file)[0])
    if tid in topics_files:
      topics_files[tid].append(file)
    else:
      topics_files[tid] = [file]
  # Extract topics
  for key, item in topics_files.items():
    # Initialize topic info
    info = {"tid":key, "title":None, "retrieval_time":None, "fid":None,
            "scrape_id":scrape_id, "posts":None, "new_posts":None,
            "complete":True, "visible_pre":None, "visible_post":None, "visible":None, "error":None}
    # Extract topic info from its files
    faulty_topic_pages, num_posts = extractTopic(scrape_path, item, info, posts, all_pids, quotes)
    for ftp in faulty_topic_pages:
      all_faulty_topic_pages.append(ftp)
    if num_posts > 0:
      topics.append(info)
    else:
      print("Note: skipped topic {} as not a single post was retrieved (topic may yet be included by a pid file)".format(key))

  # Process all pid topic page files with new posts
  for file in files_pid:
    pid = int(re.findall(r"(?<=viewtopic\.php\?pid=)\d+", file)[0])
    if pid not in all_pids: # check if last post on file referred to by pid in file name is already covered
      extractPIDPage(scrape_id, os.path.join(scrape_path, file), topics, posts, all_pids, quotes)

  for topic in topics:
    # Check if complete, and update topic info accordingly
    topic_posts = [post for post in posts if topic["tid"] == post["tid"]]
    sorted_topic_posts = sorted(topic_posts, key=lambda d: d["seq_id"])
    setPostsCompleteAndVisible(topic, sorted_topic_posts)

  # Write posts to tsv output file for each scrape to reduce RAM usage
  p_df = pd.DataFrame(posts).sort_values(["tid", "seq_id"], ascending=[True, True])
  p_df.to_csv(os.path.join(args["outdir"], posts_output_file[:-4] + "-scrape-" + str(scrape_id) + ".tsv"),
              sep='\t', float_format="%.0f", index=False)
  # Write quotes to tsv output file for each scrape to reduce RAM usage
  q_df = pd.DataFrame(quotes)
  q_df.to_csv(os.path.join(args["outdir"], quotes_output_file[:-4] + "-scrape-" + str(scrape_id) + ".tsv"),
              sep='\t', float_format="%.0f", index=False)

  return topics, all_faulty_topic_pages

#############################################################################################
# Forum extraction functions
#############################################################################################

def extractForumTopic(file, topic_raw, topic_info):
  """Extracts information on topic from raw row source obtained from forum page file.
  Parameters:
    file        - path to the file from which information is being extracted
    topic_raw   - string of the raw source 'row' containing information on the topic to extract
    topic_info  - a dictionary storing information on the topic covered by topic_raw, to update
  """
  t_raw = re.findall(r"(?<=<td class=\"tcl\">).*?</div></div>(?=</td>)", topic_raw)
  if len(t_raw) != 1:
    setForumWarning(topic_info, 31, "Irregularity in forum topic information in forum page file", file)
  else:
    tid = re.findall(r"(?<=href=\"viewtopic\.php\?id=)\d+", t_raw[0])
    if len(tid) == 0:
      setForumWarning(topic_info, 32, "Irregularity in forum topic tid information in forum page file", file)
    else:
      topic_info["tid"] = int(tid[0])
    topic_title = re.findall(r"(?<=href=\"viewtopic\.php\?id="+tid[0]+r"\">).*?(?=</a>)", t_raw[0])
    if len(topic_title) != 1:
      if topic_info["tid"] != 12146: # Exclude known exception, an actual topic with an empty title
        setForumWarning(topic_info, 33, "Missing (or too many) topic title(s) in forum page file", file)
    else:
      topic_info["topic_title"] = topic_title[0]

    first_user_info = re.findall(r"(?<=<span class=\"byuser\">by ).*?(?=</span>)", t_raw[0])
    if len(first_user_info) != 1:
      setForumWarning(topic_info, 40, "Missing (or too many) user information in forum page file", file)
    else:
      if len(re.findall(r"<span class=\"gid", first_user_info[0])) > 0:
        topic_info["first_user"] = first_user_info[0].split('>')[-1]
        first_uid = re.findall(r"(?<=href=\"profile\.php\?id=)\d+", first_user_info[0])
        if len(first_uid) == 1:
          topic_info["first_uid"] = int(first_uid[0])
        elif len(first_uid) > 1:
          setForumWarning(topic_info, 41, "Too many user id information in forum page file", file)
      else:
        topic_info["first_user"] = first_user_info[0]

  if len(re.findall(r"<span class=\"closedtext\">", topic_raw)) > 0:
    topic_info["closed"] = True
  if len(re.findall(r"<span class=\"movedtext\">", topic_raw)) > 0:
    topic_info["moved"] = True
  else:
    replies = re.findall(r"(?<=<td class=\"tc2\">)[\d,]+", topic_raw)
    views = re.findall(r"(?<=<td class=\"tc3\">)[\d,]+", topic_raw)
    lp_raw = re.findall(r"(?<=<td class=\"tcr\">).*?</span>(?=</td>)", topic_raw)
    if len(t_raw) != 1 or len(replies) != 1 or len(views) != 1 or len(lp_raw) != 1:
      setForumWarning(topic_info, 34, "Irregularity in forum topic information in forum page file", file)
    else:
      topic_info["replies"] = int(replies[0].replace(",",""))
      topic_info["views"] = int(views[0].replace(",",""))
      tpid = re.findall(r"(?<=href=\"viewtopic\.php\?pid=)\d+", lp_raw[0])
      if len(tpid) != 1:
        setForumWarning(topic_info, 35, "Irregularity in forum topic tpid information in forum page file", file)
      else:
        topic_info["tpid"] = int(tpid[0])
      lp_datetime_raw = re.findall(r"(?<=href=\"viewtopic\.php\?pid="+tpid[0]+"#p"+tpid[0]+r"\">).*?(?=</a>)", lp_raw[0])
      if len(lp_datetime_raw) != 1:
        setForumWarning(topic_info, 36, "Missing (or too many) last post date+times in forum page file", file)
      else:
        lp_datetime = lp_datetime_raw[0].split(' ')
        topic_info["lp_year"], topic_info["lp_month"], topic_info["lp_day"] = getDate(lp_datetime[0], file)
        topic_info["lp_time"] = lp_datetime[1]


      lp_user_info = re.findall(r"(?<=<span class=\"byuser\">by ).*?(?=</span>)", lp_raw[0])
      if len(lp_user_info) != 1:
        setForumWarning(topic_info, 37, "Missing (or too many) last user information in forum page file", file)
      else:
        if len(re.findall(r"<span class=\"gid", lp_user_info[0])) > 0:
          topic_info["lp_user"] = lp_user_info[0].split('>')[-1]
          lp_uid = re.findall(r"(?<=href=\"profile\.php\?id=)\d+", lp_user_info[0])
          if len(lp_uid) == 1:
            topic_info["lp_uid"] = int(lp_uid[0])
          elif len(lp_uid) > 1:
            setForumWarning(topic_info, 38, "Too many last user id information in forum page file", file)
        else:
          topic_info["lp_user"] = lp_user_info[0]

def extractForumPage(file, info, topics, all_tids, last_page):
  """Extracts various pieces of information from a single forum (page) file from a scrape
  Parameters:
    file      - path to the file from which information should be extracted
    info      - a dictionary storing information on the forum covered by this file, to update
    topics    - a list of dictionaries each storing information on a topic in this scrape/forum
    all_tids  - a list of all topic identifiers already found so far
    last_page - boolean indicating whether this file describes the last page of the topic
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setForumWarning(info, 0, "Empty forum file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body></html>", fc)) == 0:
      setForumWarning(info, 3, "Partial forum file", file)

    # Update forum information with forum title
    titles = re.findall(r"(?<=<title>).*(?= \(Page)", fc)
    if len(titles) != 1:
      setForumWarning(info, 30, "Title irregularity in forum file", file)
    elif info["title"] is None:
      info["title"] = titles[0]
    elif info["title"] != titles[0]:
      setForumWarning(info, 39, "Conflicting forum titles, overwritten with latest found in forum file", file)
      info["title"] = titles[0]

    # Extract topics and their details from this page
    topics_raw = re.findall(r"<tr class=.*?</tr>", fc)
    num_topics = len(topics_raw)
    if num_topics != 30 and info["error"] != 3 and not last_page:
      setForumWarning(info, 99, "Unexpectedly more or fewer than 30 topics in forum page file", file)
    for topic_raw in topics_raw:
      # Check that forum is not empty
      if len(re.findall(r"<div class=\"tclcon\"><div><strong>Forum is empty\.</strong></div></div>",
             topic_raw)) > 0:
        num_topics = 0
        break
      # Obtain topic information
      topic_info = {"fid":info["fid"], "tid":None,
                    # Scrape independent information
                    "topic_title":'', "retrieval_time":os.path.getmtime(file),
                    "first_user":None, "first_uid":None, "first_found":None,
                    # Scrape dependent information
                    "scrape_id":info["scrape_id"], "replies":None, "views":None, "tpid":None,
                    "lp_user":None, "lp_uid":None,
                    "lp_year":None, "lp_month":None, "lp_day":None, "lp_time":None,
                    "closed": False, "moved":False, "error":None}
      extractForumTopic(file, topic_raw, topic_info)
      # In practice topic extraction encounters no errors, thus we may ignore topics already processed previously
      if topic_info["tid"] not in all_tids:
        all_tids.append(topic_info["tid"])
        topics.append(topic_info)
        # Copy over error from topic to fora if found and there were no forum level errors
        if topic_info["error"] is not None and info["error"] is None:
          info["error"] = topic_info["error"]

    # Update forum information given knowledge of #topics covered on this page (if last page)
    if last_page:
      info["topics"] += num_topics

def extractForum(scrape_path, files, info, topics):
  """ Extracts a single forum (with potentially multiple pages) for a given scrape
  Parameters:
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to forum (page) files covering a single forum in a given scrape
    info        - a dictionary storing all forum variables/information
    topics      - a list of dictionaries each storing information on a topic in a scrape
  Returns:
    faulty_form_pages - a list of file descriptors of files that are faulty/incomplete
  """
  # Check if complete, and update topic info accordingly
  pages = []
  for it in range(1,len(files)):
    pages.append(int(re.findall(r"(?<=viewforum\.php\?id="+str(info["fid"])+r"&p=)\d+", files[it])[0]))
  pages.sort()
  if len(pages) > 0:  # Account for the case of only having a non page-numbered forum file
    info["pages"] = pages[-1]
    info["topics"] = 30 * (pages[-1]-1) # Posts on last page to be added later

  # Extract posts and other topic related information from files
  all_tids = []
  faulty_forum_pages = []
  #for file in files:
  file_extraction_dates = {}
  for file in files:
    file_extraction_dates[file] = os.path.getmtime(os.path.join(scrape_path, file))
  # Iterate over a files in order of extraction datetime
  for file, date in sorted(file_extraction_dates.items(), key=lambda item: item[1]):
    if len(files) == 1 or file == forum_file_prefix+str(info["fid"])+"&p="+str(info["pages"]):
      extractForumPage(os.path.join(scrape_path, file), info, topics, all_tids, True)
    else:
      extractForumPage(os.path.join(scrape_path, file), info, topics, all_tids, False)
  info["topics_visible"] = len(all_tids)
  if info["topics_visible"] < info["topics"]:
    info["complete"] = False

  if info["error"] is not None:
    faulty_forum_pages.append(os.path.join(scrape_path.split("/")[1],file))
  return faulty_forum_pages

def extractFora(scrape_id, scrape_path, files):
  """Extracts the fora and its associated topics of a given scrape
  Parameters:
    scrape_id   - id assigned to scrape pointed to by scrape_path
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to all forum page files from a single scrape
  Returns:
    fora                - a list of dictionaries each storing information on fora in this scrape
    fora_topics         - a list of dictionaries each storing information on a topic covered by fora
    faulty_forum_pages  - a list of file descriptors of forum page files that are faulty/incomplete
  """
  fora = []
  fora_topics = []
  all_faulty_forum_pages = []
  # Sort files into fora (grouping pages together)
  forum_files = {}
  for file in files:
    fid = int(re.findall(r"(?<=viewforum\.php\?id=)\d+", file)[0])
    if fid in forum_files:
      forum_files[fid].append(file)
    else:
      forum_files[fid] = [file]
  # Extract fora
  for key, item in forum_files.items():
    # Initialize forum info
    info = {"fid":key, "scrape_id":scrape_id, "title":None, "pages":1, "topics":0,
            "new_topics":None, "complete":True, "topics_visible":None, "error":None}
    # Extract forum info from its files
    faulty_forum_pages = extractForum(scrape_path, item, info, fora_topics)
    for ffp in faulty_forum_pages:
      all_faulty_forum_pages.append(ffp)
    fora.append(info)

  return fora, fora_topics, all_faulty_forum_pages

#############################################################################################
# Index extraction functions
#############################################################################################

def setVarIfLarger(info, var, values_list):
  """Sets the value described by the first element of value_list into dictionary info
     in field 'var' if larger than its current value.
  Parameters:
    info    - dictionary to update
    var     - name of field to update
    values_list - list of (usually) length 1, whose first element should be updated with
  """
  value = int(values_list[0].replace(",",""))
  if info[var] < value:
    info[var] = value

def extractForumIndex(file, raw, info):
  """Extracts information on a forum from raw row source obtained from index file.
  Parameters:
    file    - path to the file from which information is being extracted
    raw     - string of the raw source 'row' containing information on the forum to extract
    info    - a dictionary storing information on the forum covered by forum_raw, to update
  """
  titles = re.findall(r"(?<=viewforum\.php\?id="+str(info["fid"])+"\">).*?(?=</a>)", raw)
  if len(titles) != 1:
    setForumWarning(info, 60, "Irregularity in forum title information in index file", file)
  elif info["title"] is None:
    info["title"] = titles[0]
  elif info["title"] != titles[0]:
    # If there is a conflict, we decide on topic title based on the latest information
    extraction_time = os.path.getmtime(file)
    if extraction_time >= info["retrieval_time"]:
      setForumWarning(info, 61, "Conflicting forum titles, overwritten with latest found for index file", file)
      info["title"] = titles[0]

  descriptions = re.findall(r"(?<=<div class=\"forumdesc\">).*?(?=</div>)", raw)
  if len(descriptions) == 0:
    setForumWarning(info, 62, "Missing forum description information in index file", file)
  elif len(descriptions) > 1:
    setForumWarning(info, 63, "Irregularity in forum description information in index file", file)
  elif info["description"] is None:
    info["description"] = descriptions[0]
  elif info["description"] != descriptions[0]:
    # If there is a conflict, we decide on topic title based on the latest information
    extraction_time = os.path.getmtime(file)
    if extraction_time >= info["retrieval_time"]:
      setForumWarning(info, 64, "Conflicting forum descriptions, overwritten with latest found for index file", file)
      info["description"] = descriptions[0]


  topics = re.findall(r"(?<=<td class=\"tc2\">)[\d,]+", raw)
  posts = re.findall(r"(?<=<td class=\"tc3\">)[\d,]+", raw)
  if len(topics) != 1 or len(posts) != 1:
    setForumWarning(info, 65, "Irregularity in forum statistics in index file", file)
  else:
    # Though it should be guaranteed due to processing files in order of retrieval time
    # we make sure to get to highest statistics
    setVarIfLarger(info, "topics", topics)
    setVarIfLarger(info, "posts", posts)

def extractIndexPage(file, info, fora, date):
  """Extracts fora information and global statistics from a single forum (page) file from a scrape
  Parameters:
    file    - path to the file from which information should be extracted
    info    - a dictionary storing information on global statistics, to update
    fora    - a dictionary of dictionaries each storing information on a forum in this scrape
    date    - date that the file was last modified (according to file metadata)
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setForumWarning(info, 0, "Empty forum file", file)
      return
    if len(re.findall(r"</body></html>", fc)) == 0:
      setForumWarning(info, 3, "Partial forum file", file)

    category_blocks = re.findall(r"(?<=<div id=\"idx\d\" class=\"blocktable\">).*?(?=</tbody></table>)", fc)
    for category_block in category_blocks:
      categories = re.findall(r"(?<=<h2><span>).*?(?=</span></h2>)", category_block)
      if len(categories) != 1:
        setForumWarning(info, 4, "Irregularity in category information of index file", file)
      else:

        fora_raw = re.findall(r"<tr class=.*?</tr>", category_block)
        for forum_raw in fora_raw:
          fid = int(re.findall(r"(?<=viewforum\.php\?id=)\d+", forum_raw)[0])
          if fid not in fora: # if forum not found previously, create dictionary for it
            fora[fid] = {"fid":fid, "scrape_id":info["scrape_id"], "category":categories[0],
                         "title":None, "description":None,
                         "topics":0, "posts":0, "retrieval_time":date, "error":None}
          extractForumIndex(file, forum_raw, fora[fid])
          # Regardless whether information was overwritten we store the latest retrieval time
          fora[fid]["retrieval_time"] = date

    info["fora"] = len(fora)
    statistics_block = re.findall(r"(?=<dt><strong>Board statistics</strong></dt>).*?</dl>", fc)
    if len(statistics_block) != 1:
      setForumWarning(info, 66, "Irregularity in global statistics information in index file", file)
    else:
      users = re.findall(r"(?<=<dd><span>Total number of registered users: <strong>)[\d,]+", statistics_block[0])
      topics = re.findall(r"(?<=<dd><span>Total number of topics: <strong>)[\d,]+", statistics_block[0])
      posts = re.findall(r"(?<=<dd><span>Total number of posts: <strong>)[\d,]+", statistics_block[0])
      if len(users) != 1 or len(topics) != 1 or len(posts) != 1:
        setForumWarning(info, 67, "Irregularity in global statistics in index file", file)
      else:
        # Though it should be guaranteed due to processing files in order of retrieval time
        # we make sure to get to highest statistics
        setVarIfLarger(info, "users", users)
        setVarIfLarger(info, "topics", topics)
        setVarIfLarger(info, "posts", posts)

def extractIndex(scrape_id, scrape_path, files):
  """Extract fora information and global statistics from index files of a given scrape
  Parameters:
    scrape_id   - id assigned to scrape pointed to by scrape_path
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to all index page files from a single scrape
  Returns:
    fora       - a list of dictionaries storing information on fora in this scrape
    glob_stats - a dictionary containing some global statistics
  """
  fora = {}
  glob_stats = {"scrape_id":scrape_id, "fora":None, "topics":0, "posts":0, "users":0, "error":None}

  file_extraction_dates = {}
  for file in files:
    file_extraction_dates[file] = os.path.getmtime(os.path.join(scrape_path, file))
  # Iterate over a files in order of extraction datetime
  for file, date in sorted(file_extraction_dates.items(), key=lambda item: item[1]):
    extractIndexPage(os.path.join(scrape_path, file), glob_stats, fora, date)

  return list(fora.values()), glob_stats

#############################################################################################
# Extract forum data top-level function(s)
#############################################################################################

def extractForumData(args):
  """Extracts forum data from raw source files on scrape by scrape basis and by file type
  Parameters:
    args  - dictionary of command line arguments given
  """
  base_directory_forum = os.path.join(args["indir"], indir_forum)
  scrapes = generateScrapeIDs(base_directory_forum, os.path.join(args["outdir"], scrapes_output_file_forum))
  print(scrape_splitter)

  all_profiles = []
  all_faulty_profiles = []
  all_topics = []
  all_faulty_topic_pages = []
  all_fora = []
  all_fora_topics = []
  all_faulty_forum_pages = []
  all_index_fora = []
  all_glob_stats = []
  for scrape in scrapes:
    scrape_id = scrapes[scrape]
    print("Forum scrape {}:\n\tobtained on {}".format(scrape_id, scrape))
    print(info_splitter)
    scrape_path = os.path.join(base_directory_forum, scrape)
    scrape_contents = os.listdir(scrape_path)
    profile_files = [filename for filename in scrape_contents if filename.startswith(profile_file_prefix)]
    topic_files = [filename for filename in scrape_contents if filename.startswith(topic_file_prefix)]
    post_files = [filename for filename in scrape_contents if filename.startswith(topic_alt_file_prefix)]
    forum_files = [filename for filename in scrape_contents if filename.startswith(forum_file_prefix)]
    index_files = [filename for filename in scrape_contents if filename.startswith(index_file_prefix)]
    print("\t{:4} profile files\n\t{:4} topic files\n\t{:4} post files\n\t{:4} forum files\n\t{:4} index files".format(
      len(profile_files), len(topic_files), len(post_files), len(forum_files), len(index_files)))
    print(info_splitter)

    # Process index files
    index_fora, glob_stats = extractIndex(scrape_id, scrape_path, index_files)
    all_index_fora.append(index_fora)
    all_glob_stats.append(glob_stats)
    print("Finished extracting index files")
    print(info_splitter)
    # Process profile files
    profiles, faulty_profiles = extractProfiles(scrape_id, scrape_path, profile_files)
    all_profiles.append(profiles)
    for fp in faulty_profiles:
      all_faulty_profiles.append(fp)
    print("Finished extracting from profiles files")
    print(info_splitter)
    ####
    # Process topic files
    topics, faulty_topic_pages = extractTopics(scrape_id, scrape_path, topic_files, post_files, args)
    all_topics.append(topics)
    for ftp in faulty_topic_pages:
      all_faulty_topic_pages.append(ftp)
    print("Finished extracting from topic page files")
    print(info_splitter)
    ####
    # Process forum (page) files
    fora, fora_topics, faulty_forum_pages = extractFora(scrape_id, scrape_path, forum_files)
    all_fora.append(fora)
    all_fora_topics.append(fora_topics)
    for ftp in faulty_forum_pages:
      all_faulty_forum_pages.append(ftp)
    print("Finished extracting from forum page files")
    print(info_splitter)

    print(scrape_splitter)

  # Write profiles to tsv output file
  all_profiles_flat = [pr for sc in all_profiles for pr in sc]
  pr_df = pd.DataFrame(all_profiles_flat).sort_values(["uid", "scrape_id"], ascending=[True, True])
  pr_df.to_csv(os.path.join(os.path.join(args["outdir"]), profile_output_file), sep='\t', float_format="%.0f", index=False)
  # Provide overall profile statistics
  print("Number of scrapes with profiles: {}".format(len(all_profiles)))
  print("Total number of profiles gathered: {}".format(len(all_profiles_flat)))
  print("Faulty profiles: {}".format(all_faulty_profiles))

  # Write topics to tsv output file
  all_topics_flat = [t for sc in all_topics for t in sc]
  t_df = pd.DataFrame(all_topics_flat).sort_values(["tid", "fid", "scrape_id"], ascending=[True, True, True])
  t_df.to_csv(os.path.join(os.path.join(args["outdir"]), topics_output_file), sep='\t', float_format="%.0f", index=False)
  # Provide overall topic statistics
  print("Number of scrapes with topics: {}".format(len(all_topics)))
  print("Total number of topic pages gathered: {}".format(len(all_topics_flat)))
  print("Faulty topic pages: {}".format(all_faulty_topic_pages))

  # Write forums to tsv output file
  all_fora_flat = [f for sc in all_fora for f in sc]
  f_df = pd.DataFrame(all_fora_flat).sort_values(["fid", "scrape_id"], ascending=[True, True]).reset_index(drop=True)
  f_df.to_csv(os.path.join(os.path.join(args["outdir"]), fora_output_file), sep='\t', float_format="%.0f", index=False)
  # Write forum topics to tsv output file
  all_fora_topics_flat = [f for sc in all_fora_topics for f in sc]
  f_df = pd.DataFrame(all_fora_topics_flat).sort_values(["tid", "fid", "scrape_id"], ascending=[True, True, True])
  f_df.to_csv(os.path.join(os.path.join(args["outdir"]), fora_topic_output_file), sep='\t', float_format="%.0f", index=False)
  # Provide overall topic statistics
  print("Number of scrapes with fora: {}".format(len(all_fora)))
  print("Total number of forum pages gathered: {}".format(len(all_fora_flat)))
  print("Faulty forum pages: {}".format(all_faulty_forum_pages))

  # Write index forums to tsv output file
  all_index_fora_flat = [f for sc in all_index_fora for f in sc]
  index_fora_df = pd.DataFrame(all_index_fora_flat).sort_values(["fid", "scrape_id"], ascending=[True, True])
  index_fora_df.to_csv(os.path.join(os.path.join(args["outdir"]), index_fora_output_file), sep='\t', float_format="%.0f", index=False)
  # Write index global statistics to tsv output file
  index_df = pd.DataFrame(all_glob_stats).sort_values(["scrape_id"], ascending=[True])
  index_df.to_csv(os.path.join(os.path.join(args["outdir"]), glob_stats_output_file), sep='\t', float_format="%.0f", index=False)
  # Provide overall index statistics
  print("Number of scrapes with indices: {}".format(len(all_glob_stats)))


#############################################################################################
# Market listing extraction functions
#############################################################################################

def extractListingPageFirst(file, info):
  """Extracts various pieces of information from a single listing (page) file from a scrape
  Parameters:
    file      - path to the file from which listing information should be extracted
    info      - a dictionary storing information on the listing covered by this file, to update
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty listing file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for listing file", file)
      return
    if len(re.findall(r"<p>Greetings gwern,</p> <p>We would like to welcome you to Evolution", fc)) > 0 or len(re.findall(r"<p>Greetings simurgh,</p> <p>We would like to welcome you to Evolution", fc)) > 0:
      setMarketWarning(info, 5, "Evolution market (update) welcome message instead of listing file error", file)
      return
    if len(re.findall(r"<strong>Error!</strong> Listing could not be found", fc)) > 0:
      setMarketWarning(info, 2, "listing could not be found error in listing file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial listing file", file)

    if len(re.findall(r"<div class=\"alert alert-info\"> <strong>Notice!</strong> This listing is currently unavailable\. </div>", fc)) > 0:
      info["listing_available"] = False

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in listing page file", file)
    elif len(parent_category_block) == 1:
      cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(cid) != 1:
        setMarketWarning(info, 72, "Missing cid in listing page file", file)
      else:
        info["cid"] = cid[0]

    section = re.findall(r"(?<=<div class=\"col-md-7\">).*?(?=<div class=\"col-md-3\">)", fc)
    if len(section) != 1:
      setMarketWarning(info, 1100, "Missing listing information in listing file", file)
    else:
      # Update listing information with listing title
      titles = re.findall(r"(?<=<h\d>).*?(?=</h\d>)", section[0])
      if len(titles) < 1:
        setMarketWarning(info, 1101, "Title irregularity in listing file", file)
      else:
        info["title"] = titles[0]
      # Update listing information with seller's information
      seller_info = re.findall(r"<div class=\"seller-info.*?</div>", section[0])[0]
      info["vid"] = re.findall(r"(?<=profile/)\d+", seller_info)[0]
      info["username"] = re.findall(r"(?<=\d\">).*?(?=</a>)", seller_info)[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", seller_info)[0]
      info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      info["rank"] = re.findall(r"(?<=;\">).*?(?=</span></div>)", seller_info)[0]
      # Update listing information with price
      info["price"] = re.findall(r"(?<=BTC )\d+\.\d+?(?=</h\d>)", section[0])[0]
      # Update listing information with description
      descriptions = re.findall(r"(?<=Description</h\d> <div class=\"product-summary\"><p>).*?(?=</p></div><br />)", section[0])
      if len(descriptions) != 1:
        setMarketWarning(info, 1110, "Missing description in listing file", file)
      else:
        info["description"] = descriptions[0]
      # Update listing information with ships_to
      ships_tos = re.findall(r"(?<=<h\d>Ships To</h\d> <p>).*?(?=</p>)", section[0])
      if len(ships_tos) != 1:
        setMarketWarning(info, 1111, "Missing ships to information in listing file", file)
      else:
        info["ships_to"] = ships_tos[0]
      # Update listing information with ships_from
      ships_froms = re.findall(r"(?<=Ships From</h\d> <p>).*?(?=</p> </div>)", fc)
      if len(ships_froms) != 1:
        setMarketWarning(info, 1112, "Missing ships from information in listing file", file)
      else:
        info["ships_from"] = ships_froms[0]
      # Update listing information with product_class
      product_classes = re.findall(r"(?<=Product Class</h\d> <div class=\"tags\">).*?(?=</div>)", fc)
      if len(product_classes) != 1:
        setMarketWarning(info, 1113, "Missing product class in listing file", file)
      else:
        info["product_class"] = product_classes[0]

def extractListingsFirst(scrape_id, scrape_path, files):
  '''Extracts information on listings for an 'early' scrape (scrape_id < 7)
  Parameters:
    scrape_id   - identifier of the scrape for which we are extracting the listings
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to listing files covering a given scrape
  Returns:
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  listings = []
  for file in sorted(files):
    lid = int(file.split('/')[1])
    # Obtain listing information (note vid is vendor profile id)
    listing_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                    "scrape_id":scrape_id, "title":None, "price":None, "description":None, "listing_available":True,
                    "ships_from":None, "ships_to":None, "product_class":None, "cid":None,
                    "retrieval_time":os.path.getmtime(os.path.join(scrape_path, file)), "error":None}
    extractListingPageFirst(os.path.join(scrape_path, file), listing_info)
    if listing_info["error"] not in (0,1,2,5):
      listings.append(listing_info)
  return listings

def extractListingsSecond(scrape_id, scrape_path, files):
  '''Extracts information on listings for a 'middle' scrape (7 < scrape_id < 33)
  Parameters:
    scrape_id   - identifier of the scrape for which we are extracting the listings
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to listing files covering a given scrape
  Returns:
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  listings = []
  for file in sorted(files):
    lid = int(file.split('/')[1].split('.')[0])
    # Obtain listing information (note vid is vendor profile id)
    listing_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                    "scrape_id":scrape_id, "title":None, "price":None, "description":None, "listing_available":True,
                    "ships_from":None, "ships_to":None, "product_class":None, "cid":None,
                    "retrieval_time":os.path.getmtime(os.path.join(scrape_path, file)), "error":None}
    extractListingPageFirst(os.path.join(scrape_path, file), listing_info)
    if listing_info["error"] not in (0,1,2,5):
      listings.append(listing_info)
  return listings

def extractListingPageSecond(file, info):
  """Extracts various pieces of information from a single listing (page) file from a scrape
  Parameters:
    file      - path to the file from which listing information should be extracted
    info      - a dictionary storing information on the listing covered by this file, to update
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty listing file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for listing file", file)
      return
    if len(re.findall(r"<p>Greetings gwern,</p> <p>We would like to welcome you to Evolution", fc)) > 0 or len(re.findall(r"<p>Greetings simurgh,</p> <p>We would like to welcome you to Evolution", fc)) > 0:
      setMarketWarning(info, 5, "Evolution market (update) welcome message instead of listing file error", file)
      return
    if len(re.findall(r"<strong>Error!</strong> Listing could not be found", fc)) > 0:
      setMarketWarning(info, 2, "listing could not be found error in listing file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial listing file", file)

    if len(re.findall(r"<div class=\"alert alert-info\"> <strong>Notice!</strong> This listing is currently unavailable\. </div>", fc)) > 0:
      info["listing_available"] = False

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in listing page file", file)
    elif len(parent_category_block) == 1:
      cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(cid) != 1:
        setMarketWarning(info, 72, "Missing cid in listing page file", file)
      else:
        info["cid"] = cid[0]

    section = re.findall(r"(?<=<div class=\"col-md-8 page-product\">).*?(?=<div class=\"col-md-5\">)", fc)
    if len(section) != 1:
      setMarketWarning(info, 1100, "Missing listing information in listing file", file)
    else:
      # Update listing information with listing title
      titles = re.findall(r"(?<=<h\d><strong>).*?(?=</strong></h\d>)", section[0])
      if len(titles) < 1:
        setMarketWarning(info, 1101, "Title irregularity in listing file", file)
      else:
        info["title"] = titles[0]
      # Update listing information with seller's information
      seller_info = re.findall(r"<p>By.*?(?=<hr>)", section[0])[0]
      info["vid"] = re.findall(r"(?<=profile/)\d+", seller_info)[0]
      info["username"] = re.findall(r"(?<=\d\">).*?(?=</a>)", seller_info)[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", seller_info)[0]
      info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      info["rank"] = re.findall(r"(?<=;\">).*?(?=</span></p>)", seller_info)[0]
      # Update listing information with price
      info["price"] = re.findall(r"(?<=BTC )\d+\.\d+?(?=</strong></h\d>)", section[0])[0]
    # Update listing information with product_class
    product_classes = re.findall(r"(?<=<dt>Class</dt> <dd>).*?(?=</dd>)", fc)
    if len(product_classes) != 1:
      setMarketWarning(info, 1113, "Missing product class in listing file", file)
    else:
      info["product_class"] = product_classes[0]
    # Update listing information with ships_from
    ships_froms = re.findall(r"(?<=<dt>Ships From</dt> <dd>).*?(?=</dd>)", fc)
    if len(ships_froms) != 1:
      setMarketWarning(info, 1112, "Missing ships from information in listing file", file)
    else:
      info["ships_from"] = ships_froms[0]
    # Update listing information with description
    descriptions = re.findall(r"(?<=Description</strong></h\d> <p>).*?(?=</p><br />)", fc)
    if len(descriptions) != 1:
      setMarketWarning(info, 1110, "Missing description in listing file", file)
    else:
      info["description"] = descriptions[0]
    # Update listing information with ships_to
    ships_tos = re.findall(r"(?<=<h\d><strong>Ships To</strong></h\d> <p>).*?(?=</p>)", fc)
    if len(ships_tos) != 1:
      setMarketWarning(info, 1111, "Missing ships to information in listing file", file)
    else:
      info["ships_to"] = ships_tos[0]

def extractListingsThird(scrape_id, scrape_path, files):
  '''Extracts information on listings for a 'late' scrape (scrape_id >= 33)
  Parameters:
    scrape_id   - identifier of the scrape for which we are extracting the listings
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to listing files covering a given scrape
  Returns:
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  listings = []
  for file in sorted(files):
    lid = int(file.split('/')[1].split('.')[0])
    # Obtain listing information (note vid is vendor profile id)
    listing_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                    "scrape_id":scrape_id, "title":None, "price":None, "description":None, "listing_available":True,
                    "ships_from":None, "ships_to":None, "product_class":None, "cid":None,
                    "retrieval_time":os.path.getmtime(os.path.join(scrape_path, file)), "error":None}
    extractListingPageSecond(os.path.join(scrape_path, file), listing_info)
    if listing_info["error"] not in (0,1,2,5):
      listings.append(listing_info)
  return listings

#############################################################################################
# Market feedback pages extraction functions
#############################################################################################

month_to_number = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6,
                   "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}

def extractFeedbackPage(file, info):
  """Extracts various pieces of information from a single listing feedback (page) file from a scrape
  Parameters:
    file      - path to the file from which listing and feedback information should be extracted
    info      - a dictionary storing information on the listing covered by this file, to update
  Returns:
    feedbacks - list of dictionaries storing information on each piece of feedback extracted from the page
  """
  feedbacks = []
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty feedback file", file)
      return feedbacks
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for feedback file", file)
      return feedbacks
    if len(re.findall(r"<p>Greetings gwern,</p> <p>We would like to welcome you to Evolution", fc)) > 0 or len(re.findall(r"<p>Greetings simurgh,</p> <p>We would like to welcome you to Evolution", fc)) > 0:
      setMarketWarning(info, 5, "Evolution market (update) welcome message instead of feedback file error", file)
      return feedbacks
    if len(re.findall(r"<strong>Error!</strong> Listing could not be found", fc)) > 0:
      setMarketWarning(info, 2, "listing could not be found error in feedback file", file)
      return feedbacks
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial feedback file", file)

    if len(re.findall(r"<div class=\"alert alert-info\"> <strong>Notice!</strong> This listing is currently unavailable\. </div>", fc)) > 0:
      info["listing_available"] = False

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in feedback page file", file)
    elif len(parent_category_block) == 1:
      cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(cid) != 1:
        setMarketWarning(info, 72, "Missing cid in feedback page file", file)
      else:
        info["cid"] = cid[0]

    section = re.findall(r"(?<=<div class=\"col-md-7\">).*?(?=\">Buy It Now</button>)", fc)
    if len(section) != 1:
      setMarketWarning(info, 1100, "Missing listing information in feedback file", file)
    else:
      # Update listing information with listing title
      titles = re.findall(r"(?<=<h\d>).*?(?=</h\d>)", section[0])
      if len(titles) < 1:
        setMarketWarning(info, 1101, "Title irregularity in feedback file", file)
      else:
        info["title"] = titles[0]
      # Update listing information with seller's information
      seller_info = re.findall(r"<div class=\"seller-info.*?</div>", section[0])[0]
      info["vid"] = re.findall(r"(?<=profile/)\d+", seller_info)[0]
      info["username"] = re.findall(r"(?<=\d\">).*?(?=</a>)", seller_info)[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", seller_info)[0]
      info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      info["rank"] = re.findall(r"(?<=;\">).*?(?=</span></div>)", seller_info)[0]
      # Update listing information with price
      info["price"] = re.findall(r"(?<=BTC )\d+\.\d+?(?=</h\d>)", section[0])[0]
    # Update listing information with product_class
    product_classes = re.findall(r"(?<=;\">Product Class</h\d> <div class=\"tags\">).*?(?=</div>)", fc)
    if len(product_classes) != 1:
      setMarketWarning(info, 1113, "Missing product class in feedback file", file)
    else:
      info["product_class"] = product_classes[0]
    # Update listing information with ships_from
    ships_froms = re.findall(r"(?<=;\">Ships From</h\d> <p>).*?(?=</p> </div>)", fc)
    if len(ships_froms) != 1:
      setMarketWarning(info, 1112, "Missing ships from information in feedback file", file)
    else:
      info["ships_from"] = ships_froms[0]

    # Get feedback
    feedback_section = re.findall(r"<div class=\"pull-left feedback-header\">.*<div class=\"col-md-3\">", fc)
    if len(feedback_section) != 1:
      # Don't set error when there simply is no feedback to find
      if len(re.findall(r"<p><em>No feedback yet for this listing\.</em></p>", fc)) == 0:
        setMarketWarning(info, 1200, "Missing feedback in feedback file", file)
    else:
      fs_split = re.findall(r"(?<=<div class=\"pull-left\"><strong>).*?(?= </div> </div>  )", feedback_section[0])
      for fb in fs_split:
        feedback_info = {"lid":info["lid"], "scrape_id":info["scrape_id"],
                         "username":None, "day":None, "month":None, "year":None, "message":None}
        feedback_info["username"] = re.findall(r".*?(?=</strong></div>)", fb)[0]
        date = (re.findall(r"(?<=pull-right\">).*?(?=</div>)", fb)[0]).split(' ')
        feedback_info["day"] = int(date[1][:-1])
        feedback_info["month"] = month_to_number[date[0]]
        feedback_info["year"] = int(date[2])
        feedback_info["message"] = re.findall(r"(?<=<div class=\"panel-body\"> ).*", fb)[0]
        feedbacks.append(feedback_info)
  return feedbacks

def extractFeedback(scrape_id, scrape_path, dirs):
  '''Extracts listing and feedback information from listing feedback files
  (for scrapes with scrape_id >= 7 and scrape_id < 33)
  Parameters:
    scrape_id   - identifier of the scrape for which we are extracting listings and feedback
    scrape_path - path to scrape directory containing the files
    dirs        - list of relative paths to directories containing listing files, each covering one listing
  Returns:
    feedback_listings - a list of dictionaries storing information on listings retrieved from feedback pages
    all_feedback      - a list of dictionaries storing information on feedback retrieved from feedback pages
  '''
  feedback_listings = []
  all_feedback = []
  for d in dirs:
    lid = int(d.split('/')[1])
    listing_dir_contents = os.listdir(os.path.join(scrape_path, d))
    # Skip page 1 file as it is the same as the forum file without page identifier
    if "feedback?page=1" in listing_dir_contents and "feedback" in listing_dir_contents:
      listing_dir_contents.remove("feedback?page=1")
    for file in listing_dir_contents:
      if file.startswith('feedback'):
        # Note that the description and ships_to are not gathered, the former due to it not being available
        # and the latter because it is comprised of shipping information which can vary per destination region.
        # Furthermore, tags are also not gathered, consider also capturing tags at some point.
        listing_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                        "scrape_id":scrape_id, "title":None, "price":None, "listing_available":True,
                        "ships_from":None, "product_class":None, "cid":None,
                        "retrieval_time":os.path.getmtime(os.path.join(scrape_path, d, file)), "error":None}
        feedbacks = extractFeedbackPage(os.path.join(scrape_path, d, file), listing_info)
        if listing_info["error"] not in (0,1,2,5,6):
          feedback_listings.append(listing_info)
        for feedback in feedbacks:
          all_feedback.append(feedback)
      else:
        print("Non feedback file:", d, file)
    break
  return feedback_listings, all_feedback

def extractFeedbackPageSecond(file, info):
  """Extracts various pieces of information from a single listing feedback (page) file from a scrape
  Parameters:
    file      - path to the file from which listing and feedback information should be extracted
    info      - a dictionary storing information on the listing covered by this listing feedback file, to update
  Returns:
    feedbacks - a list of dictionaries storing information on feedback given to this listing
  """
  feedbacks = []
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty feedback file", file)
      return feedbacks
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for feedback file", file)
      return feedbacks
    if len(re.findall(r"<p>Greetings gwern,</p> <p>We would like to welcome you to Evolution", fc)) > 0 or len(re.findall(r"<p>Greetings simurgh,</p> <p>We would like to welcome you to Evolution", fc)) > 0:
      setMarketWarning(info, 5, "Evolution market (update) welcome message instead of feedback file error", file)
      return feedbacks
    if len(re.findall(r"<strong>Error!</strong> Listing could not be found", fc)) > 0:
      setMarketWarning(info, 2, "listing could not be found error in feedback file", file)
      return feedbacks
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial feedback file", file)

    if len(re.findall(r"<div class=\"alert alert-info\"> <strong>Notice!</strong> This listing is currently unavailable\. </div>", fc)) > 0:
      info["listing_available"] = False

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in feedback page file", file)
    elif len(parent_category_block) == 1:
      cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(cid) != 1:
        setMarketWarning(info, 72, "Missing cid in feedback page file", file)
      else:
        info["cid"] = cid[0]

    section = re.findall(r"(?<=<div class=\"col-md-8 page-product\">).*?(?=\">Buy It Now</button>)", fc)
    if len(section) != 1:
      setMarketWarning(info, 1100, "Missing listing information in feedback file", file)
    else:
      # Update listing information with listing title
      titles = re.findall(r"(?<=<h\d><strong>).*?(?=</strong></h\d>)", section[0])
      if len(titles) < 1:
        setMarketWarning(info, 1101, "Title irregularity in feedback file", file)
      else:
        info["title"] = titles[0]
      # Update listing information with seller's information
      seller_info = re.findall(r"<p>By.*?(?=<hr>)", section[0])[0]
      info["vid"] = re.findall(r"(?<=profile/)\d+", seller_info)[0]
      info["username"] = re.findall(r"(?<=\d\">).*?(?=</a>)", seller_info)[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", seller_info)[0]
      info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      info["rank"] = re.findall(r"(?<=;\">).*?(?=</span></p>)", seller_info)[0]
      # Update listing information with price
      info["price"] = re.findall(r"(?<=BTC )\d+\.\d+?(?=</strong></h\d>)", section[0])[0]

      # Update listing information with product_class
      product_classes = re.findall(r"(?<=<dt>Class</dt> <dd>).*?(?=</dd>)", section[0])
      if len(product_classes) != 1:
        setMarketWarning(info, 1113, "Missing product class in feedback file", file)
      else:
        info["product_class"] = product_classes[0]
      # Update listing information with ships_from
      ships_froms = re.findall(r"(?<=<dt>Ships From</dt> <dd>).*?(?=</dd>)", section[0])
      if len(ships_froms) != 1:
        setMarketWarning(info, 1112, "Missing ships from information in feedback file", file)
      else:
        info["ships_from"] = ships_froms[0]

    # Get feedback
    feedback_section = re.findall(r"<table class=\"table table-hover table-feedback\">.*</table>", fc)
    if len(feedback_section) != 1:
      # Don't set error when there simply is no feedback to find
      if len(re.findall(r"<p><em>No feedback yet for this listing\.</em></p>", fc)) == 0:
        setMarketWarning(info, 1200, "Missing feedback in feedback file", file)
    else:
      fs_split = re.findall(r"(?<=<p class=\"single\">).*?(?=</td> </tr>)", feedback_section[0])
      for fb in fs_split:
        feedback_info = {"lid":info["lid"], "scrape_id":info["scrape_id"],
                         "username":None, "day":None, "month":None, "year":None, "message":None}
        feedback_info["username"] = re.findall(r"(?<=<td class=\"user\">).*?(?=</td>)", fb)[0]
        date = (re.findall(r"(?<=<td class=\"date\">).*?(?= UTC)", fb)[0]).split(' ')
        feedback_info["day"] = int(date[1][:-1])
        feedback_info["month"] = month_to_number[date[0]]
        feedback_info["year"] = int(date[2])
        feedback_info["message"] = re.findall(r".*?(?=</p>)", fb)[0]
        feedbacks.append(feedback_info)
  return feedbacks

def extractReturnPolicyPage(file, info):
  """Extracts various pieces of information from a single listing return-policy (page) file from a scrape
  Parameters:
    file      - path to the file from which listing information should be extracted
    info      - a dictionary storing information on the listing covered by this return policy file, to update
  """
  feedbacks = []
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty return-policy file", file)
      return feedbacks
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for return-policy file", file)
      return feedbacks
    if len(re.findall(r"<p>Greetings gwern,</p> <p>We would like to welcome you to Evolution", fc)) > 0 or len(re.findall(r"<p>Greetings simurgh,</p> <p>We would like to welcome you to Evolution", fc)) > 0:
      setMarketWarning(info, 5, "Evolution market (update) welcome message instead of return-policy file error", file)
      return feedbacks
    if len(re.findall(r"<strong>Error!</strong> Listing could not be found", fc)) > 0:
      setMarketWarning(info, 2, "listing could not be found error in return-policy file", file)
      return feedbacks
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial return-policy file", file)

    if len(re.findall(r"<div class=\"alert alert-info\"> <strong>Notice!</strong> This listing is currently unavailable\. </div>", fc)) > 0:
      info["listing_available"] = False

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in return-policy file", file)
    elif len(parent_category_block) == 1:
      cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(cid) != 1:
        setMarketWarning(info, 72, "Missing cid in return-policy file", file)
      else:
        info["cid"] = cid[0]

    section = re.findall(r"(?<=<div class=\"col-md-8 page-product\">).*?(?=\">Buy It Now</button>)", fc)
    if len(section) != 1:
      setMarketWarning(info, 1100, "Missing listing information in return-policy file", file)
    else:
      # Update listing information with listing title
      titles = re.findall(r"(?<=<h\d><strong>).*?(?=</strong></h\d>)", section[0])
      if len(titles) < 1:
        setMarketWarning(info, 1101, "Title irregularity in return-policy file", file)
      else:
        info["title"] = titles[0]
      # Update listing information with seller's information
      seller_info = re.findall(r"<p>By.*?(?=<hr>)", section[0])[0]
      info["vid"] = re.findall(r"(?<=profile/)\d+", seller_info)[0]
      info["username"] = re.findall(r"(?<=\d\">).*?(?=</a>)", seller_info)[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", seller_info)[0]
      info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      info["rank"] = re.findall(r"(?<=;\">).*?(?=</span></p>)", seller_info)[0]
      # Update listing information with price
      info["price"] = re.findall(r"(?<=BTC )\d+\.\d+?(?=</strong></h\d>)", section[0])[0]

      # Update listing information with product_class
      product_classes = re.findall(r"(?<=<dt>Class</dt> <dd>).*?(?=</dd>)", section[0])
      if len(product_classes) != 1:
        setMarketWarning(info, 1113, "Missing product class in return-policy file", file)
      else:
        info["product_class"] = product_classes[0]
      # Update listing information with ships_from
      ships_froms = re.findall(r"(?<=<dt>Ships From</dt> <dd>).*?(?=</dd>)", section[0])
      if len(ships_froms) != 1:
        setMarketWarning(info, 1112, "Missing ships from information in return-policy file", file)
      else:
        info["ships_from"] = ships_froms[0]

    return_policies = re.findall(r"(?<=<h4><strong>Return Policy</strong></h4>  <p>).*?(?=</p>)", fc)
    if len(return_policies) != 1:
      setMarketWarning(info, 1120, "Missing return policy information in return-policy file", file)
    elif len(re.findall(r"does not a have return policy yet", return_policies[0])) == 0:
      info["return_policy"] = return_policies[0]

def extractFeedbackSecond(scrape_id, scrape_path, dirs):
  '''Extracts listing and feedback information from listing feedback and return-policy files
  (for scrapes with scrape_id >= 33)
  Parameters:
    scrape_id   - identifier of the scrape from which we are extracting
    scrape_path - path to scrape directory containing the files
    dirs        - list of relative paths to directories containing listing files, each covering one listing
  Returns:
    feedback_listings - a list of dictionaries storing information on listings retrieved from feedback pages
    all_feedback      - a list of dictionaries storing information on feedback retrieved from feedback pages
    rp_listing        - a list of dictionaries storing information on listings retrieved from return policy pages
  '''
  feedback_listings = []
  rp_listings = []
  all_feedback = []
  for d in dirs:
    lid = int(d.split('/')[1])
    listing_dir_contents = os.listdir(os.path.join(scrape_path, d))
    # Skip page 1 file as it is the same as the forum file without page identifier
    if "feedback?page=1" in listing_dir_contents and "feedback" in listing_dir_contents:
      listing_dir_contents.remove("feedback?page=1")
    for file in listing_dir_contents:
      if file.startswith('feedback'):
        # Note that the description and ships_to are not gathered, the former due to it not being available
        # and the latter because it is comprised of shipping information which can vary per destination region.
        # Furthermore, tags are also not gathered, consider also capturing tags at some point.
        listing_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                        "scrape_id":scrape_id, "title":None, "price":None, "listing_available":True,
                        "ships_from":None, "product_class":None, "cid":None,
                        "retrieval_time":os.path.getmtime(os.path.join(scrape_path, d, file)), "error":None}
        feedbacks = extractFeedbackPageSecond(os.path.join(scrape_path, d, file), listing_info)
        if listing_info["error"] not in (0,1,2,5,6):
          feedback_listings.append(listing_info)
        for feedback in feedbacks:
          all_feedback.append(feedback)
      elif file.startswith('return-policy'):
        rp_info = {"lid":lid, "vid":None, "username":None, "rank":None, "approval_rating":None,
                   "scrape_id":scrape_id, "title":None, "price":None, "listing_available":True,
                   "ships_from":None, "product_class":None, "cid":None, "return_policy":None,
                   "retrieval_time":os.path.getmtime(os.path.join(scrape_path, d, file)), "error":None}
        extractReturnPolicyPage(os.path.join(scrape_path, d, file), rp_info)
        if rp_info["error"] not in (0,1,2,5,6):
          rp_listings.append(rp_info)
      else:
        print("Non feedback and non return-policy file:", d, file)
  return feedback_listings, all_feedback, rp_listings

#############################################################################################
# Market profile extraction functions
#############################################################################################

def extractProfilePage(file, info, past_scrape_33_flag):
  """Extracts various pieces of information from a single profile (page) file from a scrape
  Parameters:
    file      - path to the file from which information should be extracted
    info      - a dictionary storing information on the vendor profile covered by this file, to update
    past_scrape_33_flag - boolean indicating if we are dealing with a file from scrape 33 or later
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty profile page file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for profile page file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial profile page file", file)

    usernames = re.findall(r"(?<=<div class=\"profile-header-top\"> <h\d class=\"pull-left\">).*?(?=</h\d>)", fc)
    if len(usernames) != 1:
      setMarketWarning(info, 1201, "Missing (or too many) usernames found in profile page file", file)
    else:
      info["username"] = usernames[0]

    if len(re.findall(r"This user account has been disabled\.", fc)) > 0:
      setMarketWarning({"error":None}, 7, "User account disabled for profile page", file) # output warning but do not store it as it's already stored as the variable 'disabled'!
      info["disabled"] = True
      return

    if len(re.findall(r"Feedback Ratings", fc)) == 0:   # Note this should never occur for a regular profile page file, yet it does!
      setMarketWarning(info, 8, "More or less empty profile page file", file)
    else:
      if past_scrape_33_flag:
        positive_nums = re.findall(r"(?<=<i class=\"icon-feedback-pos\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        neutral_nums  = re.findall(r"(?<=<i class=\"icon-feedback-ntl\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        negative_nums = re.findall(r"(?<=<i class=\"icon-feedback-neg\"></i> <span class=\"num\">).*?(?=</span>)", fc)
      else:
        positive_nums = re.findall(r"(?<=<i class=\"feedback-sprite feedback-pos\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        neutral_nums  = re.findall(r"(?<=<i class=\"feedback-sprite feedback-ntl\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        negative_nums = re.findall(r"(?<=<i class=\"feedback-sprite feedback-neg\"></i> <span class=\"num\">).*?(?=</span>)", fc)
      if len(positive_nums) != 1 or len(neutral_nums) != 1 or len(negative_nums) != 1:
        setMarketWarning(info, 1202, "Missing (or too many) positive/neutral/negative feedback counts in profile page file", file)
      else:
        info["positive_feedback"] = int(positive_nums[0].replace(",",""))
        info["neutral_feedback"]  = int(neutral_nums[0].replace(",",""))
        info["negative_feedback"] = int(negative_nums[0].replace(",",""))

      rank_section = re.findall(r"\.php\?title=Ranks\"\>.*<div class=\"col-md-5 profile-stats", fc)
      if len(rank_section) != 1:
        setMarketWarning(info, 1203, "Missing (or too many) rank sections found in profile page file", file)
      else:
        ranks = re.findall(r"(?<=;\">).*?(?=</span>)", rank_section[0])
        if len(ranks) != 1:
          setMarketWarning(info, 1204, "Missing (or too many) ranks found in profile page file", file)
        else:
          info["rank"] = ranks[0]

def extractProfileFiles(scrape_id, scrape_path, files, past_scrape_33_flag):
  ''' Extracts information on vendors from vendor profile pages
  Parameters:
    scrape_id           - identifier of the scrape from which we are extracting
    scrape_path         - path to scrape directory containing the files
    files               - list of relative paths to files of vendor profile pages
    past_scrape_33_flag - boolean indicating if we are dealing with a file from scrape 33 or later
  Returns:
    profiles - list of dictionaries storing information on vendor profiles retrieved from vendor profile pages
  '''
  profiles = []
  for file in sorted(files):
    vid = int(file.split('/')[1].split('.')[0])
    # Obtain listing information (note vid is profile id)
    profile_info = {"vid":vid, "username":None, "scrape_id":scrape_id, "rank":None,
                    "positive_feedback":None, "neutral_feedback":None, "negative_feedback":None,
                    "legacy_sales":None, "pgp_key":None, "return_policy":None, "disabled":False,
                    "retrieval_time":os.path.getmtime(os.path.join(scrape_path, file)), "error":None}
    extractProfilePage(os.path.join(scrape_path, file), profile_info, past_scrape_33_flag)
    if profile_info["error"] not in (0,1,2,5,6,8):
      profiles.append(profile_info)
  return profiles

#############################################################################################
# Market profile directory files extraction functions
#############################################################################################

def extractDirProfilePage(file, info, file_type_flag, past_scrape_8_flag, past_scrape_33_flag):
  """Extracts various pieces of information from a single profile (page) file from a scrape
  Parameters:
    file      - path to the file from which information should be extracted
    info      - a dictionary storing information on the feedback covered by this file, to update
    file_type_flag - boolean indicating type of flag
                     (0 = feedback file, 1 = legacy-sales file, 2 = pgp file, 3 = return-policy file)
    past_scrape_8_flag  - boolean indicating if we are dealing with a file from scrape 8 or later
    past_scrape_33_flag - boolean indicating if we are dealing with a file from scrape 33 or later
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty profile page file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for profile page file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial profile page file", file)

    usernames = re.findall(r"(?<=<div class=\"profile-header-top\"> <h\d class=\"pull-left\">).*?(?=</h\d>)", fc)
    if len(usernames) != 1:
      setMarketWarning(info, 1201, "Missing (or too many) usernames found in profile page file", file)
    elif info["username"] is None:
      info["username"] = usernames[0]
    elif info["username"] != usernames[0]:
      setMarketWarning(info, 1211, "Conflicting usernames found in profile page file", file)
      info["username"] = usernames[0]

    if len(re.findall(r"This user account has been disabled\.", fc)) > 0:
      setMarketWarning({"error":None}, 7, "User account disabled for profile page", file) # output warning but do not store it as it's already stored as the variable 'disabled'!
      info["disabled"] = True
      return

    if len(re.findall(r"Feedback Ratings", fc)) == 0:
      setMarketWarning(info, 8, "More or less empty profile page file", file)
    else:
      if past_scrape_33_flag:
        positive_nums = re.findall(r"(?<=<i class=\"icon-feedback-pos\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        neutral_nums  = re.findall(r"(?<=<i class=\"icon-feedback-ntl\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        negative_nums = re.findall(r"(?<=<i class=\"icon-feedback-neg\"></i> <span class=\"num\">).*?(?=</span>)", fc)
      else:
        positive_nums = re.findall(r"(?<=<i class=\"feedback-sprite feedback-pos\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        neutral_nums  = re.findall(r"(?<=<i class=\"feedback-sprite feedback-ntl\"></i> <span class=\"num\">).*?(?=</span>)", fc)
        negative_nums = re.findall(r"(?<=<i class=\"feedback-sprite feedback-neg\"></i> <span class=\"num\">).*?(?=</span>)", fc)
      if len(positive_nums) != 1 or len(neutral_nums) != 1 or len(negative_nums) != 1:
        setMarketWarning(info, 1202, "Missing (or too many) positive/neutral/negative feedback counts in profile page file", file)
      else:
        if info["positive_feedback"] is None:
          info["positive_feedback"] = int(positive_nums[0].replace(",",""))
          info["neutral_feedback"]  = int(neutral_nums[0].replace(",",""))
          info["negative_feedback"] = int(negative_nums[0].replace(",",""))
        else:
          positive_feedback = int(positive_nums[0].replace(",",""))
          if positive_feedback > info["positive_feedback"]:
            info["positive_feedback"] = positive_feedback
          neutral_feedback = int(neutral_nums[0].replace(",",""))
          if neutral_feedback > info["neutral_feedback"]:
            info["neutral_feedback"] = neutral_feedback
          negative_feedback = int(negative_nums[0].replace(",",""))
          if negative_feedback > info["negative_feedback"]:
            info["negative_feedback"] = negative_feedback

      rank_section = re.findall(r"\.php\?title=Ranks\"\>.*<div class=\"col-md-5 profile-stats", fc)
      if len(rank_section) != 1:
        setMarketWarning(info, 1203, "Missing (or too many) rank sections found in profile page file", file)
      else:
        ranks = re.findall(r"(?<=;\">).*?(?=</span>)", rank_section[0])
        if len(ranks) != 1:
          setMarketWarning(info, 1204, "Missing (or too many) ranks found in profile page file", file)
        elif info["rank"] is None:
          info["rank"] = ranks[0]
        elif info["rank"] != ranks[0]:
          if (ranks[0] in early_rank_order and early_rank_order[ranks[0]] > early_rank_order[info["rank"]]) \
             or (ranks[0][:5] == "Level" and ranks[0] > info["rank"]):
             info["rank"] = ranks[0]

    if file_type_flag == 1:
      if past_scrape_33_flag:
        legacy_sales_section = re.findall(r"(?<=</ul><br />).*?(?=</div>)", fc)
      else:
        legacy_sales_section = re.findall(r"(?<=<div class=\"profile-container\">).*?(?=</div>)", fc)
      if len(legacy_sales_section) != 1:
        setMarketWarning(info, 1205, "Missing legacy sales section in legacy-sales profile page file", file)
      elif len(re.findall(r"does not have any Legacy Sales", legacy_sales_section[0])) == 0:
        legacy_sales = re.findall(r"Confirmed.*?(?=</p>)", legacy_sales_section[0])
        if len(legacy_sales) < 1:
          setMarketWarning(info, 1206, "Missing legacy sales information in legacy-sales profile page file", file)
          print(legacy_sales_section[0])
        else:
          info["legacy_sales"] = ""
          for ls in legacy_sales:
            info["legacy_sales"] += ls

    if file_type_flag == 2:
      if past_scrape_33_flag:
        pgp_section = re.findall(r"(?<=</ul><br />).*?(?=</div>)", fc)
      else:
        pgp_section = re.findall(r"(?<=<div class=\"profile-container\">).*?(?=</div>)", fc)
      if len(pgp_section) != 1:
        setMarketWarning(info, 1207, "Missing pgp_key section in pgp profile page file", file)
      elif len(re.findall(r"No PGP key available", pgp_section[0])) == 0 and len(re.findall(r"does not have a PGP key", pgp_section[0])) == 0:
        pgp_keys = re.findall(r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-+END PGP PUBLIC KEY BLOCK-+", fc)
        if len(pgp_keys) == 0:
          pgp_keys = re.findall(r"-----BEGIN PGP PRIVATE KEY BLOCK-----.*?-+END PGP PRIVATE KEY BLOCK-+", fc)
          if len(pgp_keys) == 0: # To account for the one vendor who used BEGIN at the end as well instead of END
            pgp_keys = re.findall(r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-+BEGIN PGP PUBLIC KEY BLOCK-+", fc)
        if len(pgp_keys) < 1:
          setMarketWarning(info, 1217, "Irregularity in pgp_key in pgp profile page file", file)
        else:
          info["pgp_key"] = pgp_keys[0]

    if file_type_flag == 3:
      if past_scrape_33_flag:
        return_policy_section = re.findall(r"(?<=</ul><br />).*?(?=</div>)", fc)
      else:
        return_policy_section = re.findall(r"(?<=<div class=\"profile-container\">).*?(?=</div>)", fc)
      if len(return_policy_section) != 1:
        setMarketWarning(info, 1208, "Missing return policy section in return-policy profile page file", file)
      elif len(re.findall(r"does not a have return policy yet", return_policy_section[0])) == 0:
        if past_scrape_8_flag:
          return_policies = re.findall(r"(?<=<p>).*?(?=</p>)", return_policy_section[0])
          if len(return_policies) != 1:
            setMarketWarning(info, 1209, "Irregularity for return policy for return-policy profile page file", file)
          else:
            info["return_policy"] = return_policies[0]
        else:
          info["return_policy"] = return_policy_section[0].strip()

def extractProfileDirs(scrape_id, scrape_path, dirs, past_scrape_8_flag, past_scrape_33_flag):
  ''' Extracts vendor profile information from various types of source files
  Parameters:
    scrape_id     - identifier of the scrape from which we are extracting (thus from which dirs was obtained)
    scrape_path   - path to scrape directory containing the files
    dirs          - list of relative paths to directories containing profile files, each covering one vendor/profile
    past_scrape_8_flag  - boolean indicating if we are dealing with a file from scrape 8 or later
    past_scrape_33_flag - boolean indicating if we are dealing with a file from scrape 33 or later
  Returns:
    profiles - a list of dictionaries storing information on the extracted profiles
  '''
  profiles = []
  for d in dirs:
    vid = int(d.split('/')[1])
    profile_dir_contents = os.listdir(os.path.join(scrape_path, d))

    useful_flag = False
    for file in profile_dir_contents:
      file_path = os.path.join(scrape_path, d, file)
      profile_info = {"vid":vid, "username":None, "scrape_id":scrape_id, "rank":None,
                      "positive_feedback":None, "neutral_feedback":None, "negative_feedback":None,
                      "legacy_sales":None, "pgp_key":None, "return_policy":None, "disabled":False,
                      "retrieval_time":os.path.getmtime(file_path), "error":None}
      if file == "legacy-sales":
        extractDirProfilePage(file_path, profile_info, 1, past_scrape_8_flag, past_scrape_33_flag)
      elif file == "pgp":
        extractDirProfilePage(file_path, profile_info, 2, past_scrape_8_flag, past_scrape_33_flag)
      elif file == "return-policy":
        extractDirProfilePage(file_path, profile_info, 3, past_scrape_8_flag, past_scrape_33_flag)
      else:
        extractDirProfilePage(file_path, profile_info, 0, past_scrape_8_flag, past_scrape_33_flag)
      if profile_info["error"] not in (0, 1):
        profiles.append(profile_info)
        useful_flag = True
    if not useful_flag:
      print("Note: skipped profile directory {}".format(os.path.join(scrape_path.split("/")[-1], d)))
  return profiles

#############################################################################################
# Market category pages extraction functions
#############################################################################################

def extractCategoryFile(file, info, listings, extraction_date, scrape_id):
  """Extracts various pieces of information from a single category (page) file from a scrape
  Parameters:
    file      - path to the file from which information should be extracted
    info      - a dictionary storing information on the category covered by this file, to update
    listings  - list of dictionaries storing information on extracted listings, to update with newly extracted listings
    extraction_date - date that the file was last modified (according to file metadata)
    scrape_id - identifier of the scrape to which this file belongs
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning(info, 0, "Empty category page file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning(info, 1, "Scraper was logged out for category page file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning(info, 3, "Partial category page file", file)

    category_names = re.findall(r"(?<=class\=\"active\">)\w[^<]*?(?=</li>)", fc)
    if len(category_names) != 1:
      setMarketWarning(info, 70, "Missing active category in category page file", file)
    else:
      info["category"] = category_names[0]

    parent_category_block = re.findall(r"category/\d+\">\w[^<]*?</a></li>\s*<li class=\"active\"", fc)
    if len(parent_category_block) > 1:
      setMarketWarning(info, 71, "Too many parent category blocks in category page file", file)
    elif len(parent_category_block) == 1:
      parent_cid = re.findall(r"(?<=category/)\d+", parent_category_block[0])
      if len(parent_cid) != 1:
        setMarketWarning(info, 72, "Missing parent cid in category page file", file)
      else:
        info["parent_cid"] = parent_cid[0]
      parent_category = re.findall(r"(?<=>).*?(?=</a>)", parent_category_block[0])
      if len(parent_category) != 1:
        setMarketWarning(info, 73, "Missing parent category in category page file", file)
      else:
        info["parent_category"] = parent_category[0]

    listings_block = re.findall(r"(?<=details\">).*?(?=Add to Favorites)", fc)
    if len(listings_block) == 0:
      listings_block = re.findall(r"(?<=details\">).*?(?=Buy It Now)", fc)
    if len(listings_block) == 0:
      setMarketWarning({"error":None}, 74, "Missing listing block in category page file", file)
    for listing_block in listings_block:
      listing_info = {"lid":None, "vid":None, "username":None, "rank":None, "approval_rating":None,
                      "scrape_id":scrape_id, "title":None, "price":None, "store_description":None, "product_class":None,
                      "cid":info["cid"], "retrieval_time":extraction_date, "error":None}

      listing_info["lid"] = int(re.findall(r"(?<=listing/)\d+", listing_block)[0])
      listing_info["title"] = re.findall(r"(?<=listing/"+str(listing_info["lid"])+"\">).*?(?=</a>)", listing_block)[0]
      descriptions = re.findall(r"(?<=product-description\">)[^<]+?(?=</div>)", listing_block)
      if len(descriptions) != 0: # descriptions not available after scrape 6
        listing_info["store_description"] = descriptions[0]
      price = re.findall(r"(?<=>BTC )\d+\.\d+", listing_block)
      if len(price) == 0:
        price = re.findall(r"(?<=BTC</strong></span> )\d+\.\d+", listing_block)
        # if len(price) == 0:
        #   price = re.findall(r"(?<=\"price\">BTC )\d+\.\d+", listing_block)
      listing_info["price"] = price[0]
      product_classes = re.findall(r"(?<=title=\")\w+(?= product\")", listing_block)
      if len(product_classes) != 0: # info not available before scrape 7
        listing_info["product_class"] = product_classes[0]

      vendor_block = re.findall(r"profile/.*?</span>", listing_block)
      listing_info["vid"] = re.findall(r"(?<=profile/)\d+", vendor_block[0])[0]
      listing_info["username"] = re.findall(r"(?<=profile/"+str(listing_info["vid"])+"\">).*?(?=</a>)", vendor_block[0])[0]
      listing_info["rank"] = re.findall(r"(?<=;\">).*?(?=</span>)", vendor_block[0])[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", vendor_block[0])[0]
      listing_info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      listings.append(listing_info)

def extractCategoryFiles(scrape_id, scrape_path, files):
  ''' Extracts listing and vendor information from category source files
  Parameters:
    scrape_id   - identifier of the scrape from which we are extracting
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to listing files covering a given scrape
  Returns:
    categories  - list of dictionaries storing information on the categories covered/extracted form 'files'
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  categories = []
  listings = []

  for file in files:
    cid = int(file.split('/')[1].split('?')[0])
    file_extraction_date = os.path.getmtime(os.path.join(scrape_path, file))

    category_info = {"cid":cid, "category":None, "parent_cid":None, "parent_category":None, "error":None}#,
                     #"scrape_id":scrape_id, "listings":None}
    extractCategoryFile(os.path.join(scrape_path, file), category_info, listings, file_extraction_date, scrape_id)
    if category_info["error"] not in (0,1,2,5):
      categories.append(category_info)

  return categories, listings

#############################################################################################
# Market store pages extraction functions
#############################################################################################

def extractStoreFile(file, listings, extraction_date, scrape_id, vid, cid=None):
  """Extracts listing information from a store page, which covers listings for a single vendor (and product category)
  Parameters:
    file            - path to the file from which information should be extracted
    listings        - list of dictionaries storing information on listings to which records on listings
                      on this page are to be added
    extraction_date - date that the file was last modified (according to file metadata)
    scrape_id       - identifier of the scrape to which this file belongs
    vid             - vendor identifier whose listings are covered by this store page
    cid             - product category identifier for which listings are covered by this store page (when applicable)
  """
  with open(file, 'r') as f:
    file_contents = f.read()
    fc = re.sub(r"[\n\t]", "", file_contents)
    # Check if the file is empty
    if len(fc) == 0:
      setMarketWarning({"error":None}, 0, "Empty category page file", file)
      return
    # Check if an error was encountered
    if len(re.findall(r"<title>   Evolution  :: Login  </title>", fc)) > 0:
      setMarketWarning({"error":None}, 1, "Scraper was logged out for category page file", file)
      return
    # Check if only part of the file is available
    if len(re.findall(r"</body>\s{0,1}</html>", fc)) == 0:
      setMarketWarning({"error":None}, 3, "Partial category page file", file)

    # Determine listing blocks, and extract listing information from each block
    listings_block = re.findall(r"(?<=details\">).*?(?=Add to Favorites)", fc)
    if len(listings_block) == 0:
      listings_block = re.findall(r"(?<=details\">).*?(?=Buy It Now)", fc)
    if len(listings_block) == 0:
      setMarketWarning({"error":None}, 84, "Missing listing block in store page file", file)
    for listing_block in listings_block:
      listing_info = {"lid":None, "vid":vid, "username":None, "rank":None, "approval_rating":None,
                      "scrape_id":scrape_id, "title":None, "price":None, "store_description":None, "product_class":None,
                      "cid":cid, "retrieval_time":extraction_date, "error":None}
      # Extract listing information from each block
      listing_info["lid"] = int(re.findall(r"(?<=listing/)\d+", listing_block)[0])
      listing_info["title"] = re.findall(r"(?<=listing/"+str(listing_info["lid"])+"\">).*?(?=</a>)", listing_block)[0]
      descriptions = re.findall(r"(?<=product-description\">)[^<]+?(?=</div>)", listing_block)
      if len(descriptions) != 0: # descriptions not available after scrape 6
        listing_info["store_description"] = descriptions[0]
      price = re.findall(r"(?<=>BTC )\d+\.\d+", listing_block)
      if len(price) == 0:
        price = re.findall(r"(?<=BTC</strong></span> )\d+\.\d+", listing_block)
        listing_info["price"] = price[0]
      product_classes = re.findall(r"(?<=title=\")\w+(?= product\")", listing_block)
      if len(product_classes) != 0: # info not available before scrape 7
        listing_info["product_class"] = product_classes[0]

      vendor_block = re.findall(r"profile/.*?</span>", listing_block)
      if vid != int(re.findall(r"(?<=profile/)\d+", vendor_block[0])[0]):
        setMarketWarning(listing_info, 80, "Mismatch of extracted vid with file indicated vid for store page file", file)
      listing_info["username"] = re.findall(r"(?<=profile/"+str(vid)+"\">).*?(?=</a>)", vendor_block[0])[0]
      listing_info["rank"] = re.findall(r"(?<=;\">).*?(?=</span>)", vendor_block[0])[0]
      approval_rating = re.findall(r"(?<=</a> \(\s).*?(?= \))", vendor_block[0])[0]
      listing_info["approval_rating"] = (float(approval_rating[:-1]) if approval_rating != 'n/a' else None)
      listings.append(listing_info)

def extractStoreFiles(scrape_id, scrape_path, files):
  ''' Extracts listing and vendor information from store source files
  Parameters:
    scrape_id   - identifier of the scrape from which we are extracting
    scrape_path - path to scrape directory containing the files
    files       - list of relative paths to store files covering a given scrape
  Returns:
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  listings = []

  for file in files:
    vid = int(file)
    file_extraction_date = os.path.getmtime(os.path.join(scrape_path, file))
    extractStoreFile(os.path.join(scrape_path, file), listings, file_extraction_date, scrape_id, vid)

  return listings

def extractStoreDirectories(scrape_id, scrape_path, dirs):
  ''' Extracts listing and vendor information from store source files
  Parameters:
    scrape_id   - identifier of the scrape from which we are extracting
    scrape_path - path to scrape directory containing the files
    dirs        - list of relative paths directories with store files covering a given scrape
  Returns:
    listings    - list of dictionaries storing information on the listings covered/extracted from 'files'
  '''
  listings = []

  for store_dir in dirs:
    vid = int(store_dir.split('/')[1])
    dir_contents = os.listdir(os.path.join(scrape_path, store_dir))
    dir_files = [os.path.join(store_dir, filename) for filename in dir_contents if os.path.isfile(os.path.join(scrape_path, store_dir, filename))]
    for file in dir_files:
      cid = int(file.split('/')[2].split('?')[0])
      file_extraction_date = os.path.getmtime(os.path.join(scrape_path, file))
      extractStoreFile(os.path.join(scrape_path, file), listings, file_extraction_date, scrape_id, vid, cid)

  return listings

#############################################################################################
# Extract Market data top-level function(s)
#############################################################################################

def extractMarketData(args):
  """Extracts market data from raw source files on scrape by scrape basis and per file type
  Parameters:
    args  - dictionary of command line arguments given
  """
  base_directory_market = os.path.join(args["indir"], indir_market)
  scrapes = generateScrapeIDs(base_directory_market, os.path.join(args["outdir"], scrapes_output_file_market))
  print(scrape_splitter)

  all_listings = []
  all_feedback_listings = []
  all_feedback = []
  all_rp_listings = []
  all_profiles = []
  all_categories = []
  all_category_listings = []
  all_store_listings = []
  for scrape in scrapes:
    scrape_id = scrapes[scrape]
    print("Market scrape {}:\n\tobtained on {}".format(scrape_id, scrape))
    print(info_splitter)
    scrape_path = os.path.join(base_directory_market, scrape)
    scrape_contents = os.listdir(scrape_path)
    if "listing" not in scrape_contents:
      print("Error: missing listing directory")
    else:
      if scrape_id < 7: # only files
        listing_contents = os.listdir(os.path.join(scrape_path, "listing"))
        listing_files = ["listing/" + filename for filename in listing_contents]
        listings = extractListingsFirst(scrape_id, scrape_path, listing_files)
        for listing in listings:
          all_listings.append(listing)
      elif scrape_id < 33:
        listing_contents = os.listdir(os.path.join(scrape_path, "listing"))
        listing_files = ["listing/" + filename for filename in listing_contents if os.path.isfile(os.path.join(scrape_path, "listing/", filename))]
        listing_directories = ["listing/" + directory for directory in listing_contents if os.path.isdir(os.path.join(scrape_path, "listing/", directory))]
        listings = extractListingsSecond(scrape_id, scrape_path, listing_files)
        for listing in listings:
          all_listings.append(listing)
        feedback_listings, feedbacks = extractFeedback(scrape_id, scrape_path, listing_directories)
        for fl in feedback_listings:
          all_feedback_listings.append(fl)
        for feedback in feedbacks:
          all_feedback.append(feedback)
      else:
        listing_contents = os.listdir(os.path.join(scrape_path, "listing"))
        listing_files = ["listing/" + filename for filename in listing_contents if os.path.isfile(os.path.join(scrape_path, "listing/", filename))]
        listing_directories = ["listing/" + directory for directory in listing_contents if os.path.isdir(os.path.join(scrape_path, "listing/", directory))]
        listings = extractListingsThird(scrape_id, scrape_path, listing_files)
        for listing in listings:
          all_listings.append(listing)
        feedback_listings, feedbacks, rp_listings = extractFeedbackSecond(scrape_id, scrape_path, listing_directories)
        for fl in feedback_listings:
          all_feedback_listings.append(fl)
        for feedback in feedbacks:
          all_feedback.append(feedback)
        for rp_listing in rp_listings:
          all_rp_listings.append(rp_listing)
      print("Finished extracting from listing files")
    print(info_splitter)
    if "profile" not in scrape_contents:
      print("Error: missing profile directory")
    else:
      profile_contents = os.listdir(os.path.join(scrape_path, "profile"))
      profile_files = ["profile/" + filename for filename in profile_contents if os.path.isfile(os.path.join(scrape_path, "profile/", filename))]
      # For normal files we can't obtain 'legacy sales', 'pgp-key' or 'return policy' information. Additionally check for 'vendor since' too?
      profile_directories = ["profile/" + directory for directory in profile_contents if os.path.isdir(os.path.join(scrape_path, "profile/", directory))]
      # Directories, prioritise the legacy-sales file, only look further if info incomplete there (due to some issue with the file)
      if scrape_id < 8:
        profiles = extractProfileFiles(scrape_id, scrape_path, profile_files, False)
        profiles_dir = extractProfileDirs(scrape_id, scrape_path, profile_directories, False, False)
      elif scrape_id < 33:
        profiles = extractProfileFiles(scrape_id, scrape_path, profile_files, False)
        profiles_dir = extractProfileDirs(scrape_id, scrape_path, profile_directories, True, False)
      else:
        profiles = extractProfileFiles(scrape_id, scrape_path, profile_files, True)
        profiles_dir = extractProfileDirs(scrape_id, scrape_path, profile_directories, True, True)
      for profile in profiles:
        all_profiles.append(profile)
      for profile in profiles_dir:
        all_profiles.append(profile)
      print("Finished extracting from profile files")
    print(info_splitter)
    if "category" not in scrape_contents:
      print("Error: missing category directory")
    else:
      category_contents = os.listdir(os.path.join(scrape_path, "category"))
      category_files = ["category/" + filename for filename in category_contents]
      categories, listings = extractCategoryFiles(scrape_id, scrape_path, category_files)
      for category in categories:
        all_categories.append(category)
      for listing in listings:
        all_category_listings.append(listing)
      print("Finished extracting from category files")
    print(info_splitter)
    if "store" not in scrape_contents:
      print("Error: missing store directory")
    else:
      store_contents = os.listdir(os.path.join(scrape_path, "store"))
      store_files = ["store/" + filename for filename in scrape_contents if os.path.isfile(os.path.join(scrape_path, "store/", filename))]
      store_directories = ["store/" + directory for directory in store_contents if os.path.isdir(os.path.join(scrape_path, "store/", directory))]
      listings = extractStoreFiles(scrape_id, scrape_path, store_files)
      for listing in listings:
        all_store_listings.append(listing)
      listings = extractStoreDirectories(scrape_id, scrape_path, store_directories)
      for listing in listings:
        all_store_listings.append(listing)
      print("Finished extracting from store files")
    print(scrape_splitter)

  df_listings = pd.DataFrame(all_listings)
  df_listings["approval_rating"] = df_listings["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  df_listings["approval_rating"] = df_listings["approval_rating"].replace('nan', np.nan)
  df_listings.to_csv(os.path.join(args["outdir"], listings_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_listings)

  df_feedback_listings = pd.DataFrame(all_feedback_listings)
  df_feedback_listings["approval_rating"] = df_feedback_listings["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  df_feedback_listings.to_csv(os.path.join(args["outdir"], feedback_listings_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_feedback_listings)

  df_feedback = pd.DataFrame(all_feedback)
  df_feedback.to_csv(os.path.join(args["outdir"], feedback_output_file), sep='\t', float_format="%.0f")
  print(df_feedback)

  df_rp_listings = pd.DataFrame(all_rp_listings)
  df_rp_listings["approval_rating"] = df_rp_listings["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  df_rp_listings.to_csv(os.path.join(args["outdir"], rp_listings_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_rp_listings)

  df_profiles = pd.DataFrame(all_profiles)
  df_profiles.to_csv(os.path.join(args["outdir"], profiles_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_profiles)

  df_categories = pd.DataFrame(all_categories).drop(columns="error").drop_duplicates().sort_values(["cid"], ascending=[True])
  df_categories.to_csv(os.path.join(args["outdir"], categories_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_categories)

  df_category_listings = pd.DataFrame(all_category_listings).sort_values(["lid", "scrape_id", "cid"], ascending=[True, True, True])
  df_category_listings["approval_rating"] = df_category_listings["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  #df_category_listings["approval_rating"] = df_category_listings["approval_rating"].replace('nan', np.nan)
  df_category_listings.to_csv(os.path.join(args["outdir"], category_listings_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_category_listings)

  df_store_listings = pd.DataFrame(all_store_listings).sort_values(["lid", "scrape_id", "cid"], ascending=[True, True, True])
  df_store_listings["approval_rating"] = df_store_listings["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  #df_store_listings["approval_rating"] = df_store_listings["approval_rating"].replace('nan', np.nan)
  df_store_listings.to_csv(os.path.join(args["outdir"], store_listings_output_file), sep='\t', float_format="%.0f", index=False)
  print(df_store_listings)

#############################################################################################
# Main function
#############################################################################################

if __name__ == "__main__":
  sys.stdout = Logger()
  start_time = timeit.default_timer()

  # Process command line input to obtain input and output base directories
  input_parser = InputParser()
  args = input_parser.getInputArgumentsAsDict()
  os.makedirs(os.path.join(args["outdir"], "extracted-unrefined/"), exist_ok=True)

  # Extract forum and market data from raw source files
  extractForumData(args)
  extractMarketData(args)

  stop_time = timeit.default_timer()
  print("Total runtime: {}s".format(stop_time - start_time))
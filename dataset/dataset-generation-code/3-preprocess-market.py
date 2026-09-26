import numpy as np
import pandas as pd
import timeit

import re
import math
from itertools import combinations

import argparse
import sys
import os

#############################################################################################
# set some global variables
#############################################################################################

# output information splitters
scrape_splitter = "================================="

# Filenames for extracted data to preprocess
scrapes_file_market = "market-scrapes.tsv"
categories_file     = "market-categories.tsv"
listings_file           = "market-listings.tsv"
feedback_listings_file  = "market-feedback-listings.tsv"
rp_listings_file        = "market-rp-listings.tsv"
category_listings_file  = "market-category-listings.tsv"
store_listings_file     = "market-store-listings.tsv"

feedback_file       = "market-feedback.tsv"
profiles_file       = "market-profiles.tsv"

# Filenames for outputting preprocessed data to
scrapes_file          = "market/scrapes.tsv"
profiles_out_file     = "market/vendors.tsv"
listings_out_file     = "market/listings.tsv"
categories_out_file   = "market/categories.tsv"
feedback_out_file     = "market/listing-feedback.tsv"

# Filename of forum user preprocessed data
forum_profile_file              = "forum/user.tsv"
# Filename for outputting forum user and market vendor matching results
market_forum_user_matching_file = "forum-market/user-matching.tsv"

# Vendor rank ordering used up to market scrape 13
early_rank_order = {"Freshman": 1, "Sophomore": 2, "Junior": 3, "Senior": 4, "Premium": 5,
                    "Advanced": 6, "Expert": 7, "Master": 8, "Grandmaster": 9, "Godlike": 10}

#############################################################################################
# Logger functions
#############################################################################################
original_stdout = sys.stdout # So we may revert to normal stdout behaviour whenever we want

class Logger(object):
  def __init__(self):
    self.terminal = sys.stdout
    self.log = open("logfile-preproc-market.log", "w")

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
    self.parser = argparse.ArgumentParser(description="Preprocesses extracted market data by combining the various data sources and resolving various data quality issues. Resultant data is stored in specified output directory.")
    self.setArguments()
    self.printInput()

  def setArguments(self):
    self.parser.add_argument('-in', "--indir", required=True, help="Location of base directory where extracted data was stored during first step, i.e., initial output directory")
    self.parser.add_argument('-out', "--outdir", required=True, help="Location of base directory where preprocessed and resolved data should be stored (same as previous step!)")

  def getInputArgumentsAsDict(self):
    return vars(self.parser.parse_args())

  def printInput(self):
    args = self.getInputArgumentsAsDict()
    print(scrape_splitter)
    for label in args.keys():
      print("{}: {}".format(self.parser._option_string_actions["--" +label].help, args[label]))
    print(scrape_splitter + "\n")

#############################################################################################
# Categories preprocessing function
#############################################################################################

def resolveCategoryConflicts(dfus, info, var, warning_info, df_cat=None):
  '''Determines whether there are any conflicts for a given variable and (if known) resolves them
     by choosing the option with the 'latest' retrieval time
  Parameters:
    dfus         - List of panda dataframes within which the variable must be checked for conflicts
    info         - Dictionary in which the resolved variable must be stored
    var          - Variable (string) for which conflicts must be checked
    warning_info - String used in warnings to identify the exact instance for which the warning occurs
    df_cat       - Dictionary of not yet resolved category data (thus with all options for parent categories)
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x and x != ''}
  if len(var_set) > 1:
    # Resolve, if applicable, known category name conflicts
    if "Disassociatives" in var_set:
      var_set.remove("Disassociatives")
    if "Paraphernalia" in var_set:
      var_set.remove("Paraphernalia")
    if len(var_set) == 1:
      info[var] = list(var_set)[0]
    else: # Otherwise,
      if var in ["parent_cid", "parent_category"]:
        # If multiple parent category id's possible, choose the child option (i.e., the most specific option)
        remove_parents = []
        for option in var_set:
          parents = df_cat.loc[df_cat[var[7:]] == option][var].unique()
          for parent in parents:
            if parent in var_set:
              remove_parents.append(parent)
        for parent in remove_parents:
          var_set.remove(parent)
        if len(var_set) > 1: # Unknown parent category conflict
          print("Warning (7): Multiple {} information for {}. Options are {}. Last retrieved ({}) chosen.".format(var, warning_info, var_set, info[var]))
        else:
          info[var] =list(var_set)[0]
      else: # Previously unknown product category name conflict
        info[var] = list(var_set)[0]
        print("Warning (8): Multiple {} information for {}. Options are {}. Option ({}) chosen.".format(var, warning_info, var_set, info[var]))
  elif len(var_set) == 1:
    info[var] = list(var_set)[0]
  elif var not in ["parent_cid", "parent_category"]: # These types of information can often be missing as they are only included in certain files, which may not always have been retrieved
    print("Warning (9): Missing {} information for {}".format(var, warning_info))

def resolveCategories(args):
  '''Resolves market product category data, creating a proper hierarchical tree of product categories
  Parameters:
    args - dictionary of command line arguments given
    Returns: a dataframe with combined and resolved market product category information
  '''
  # Retrieve extracted market product category data and determine all product category identifiers
  df_categories = pd.read_csv(os.path.join(args["indir"], categories_file), sep='\t', index_col=False).drop_duplicates()
  all_cids = sorted(list(df_categories["cid"].unique()))

  # Resolve product category data one category identifier at a time
  all_categories = []
  for cid in all_cids:
    cat_info = {"cid":cid, "category":None, "parent_cid":None, "parent_category":None}
    dfc_cat = df_categories.loc[df_categories["cid"] == cid]

    # Resolve category name and parent category (tree structure based)
    warning_info = "cid = {}".format(cid)
    resolveCategoryConflicts([dfc_cat], cat_info, "category", warning_info)
    resolveCategoryConflicts([dfc_cat], cat_info, "parent_cid", warning_info, df_categories)
    resolveCategoryConflicts([dfc_cat], cat_info, "parent_category", warning_info, df_categories)
    all_categories.append(cat_info)

  # Store and return a dataframe with the resolved market product category data. The parent category name is dropped as that can
  # be looked up elsewhere within the same data using the parent category identifier.
  df_cat_resolved = pd.DataFrame(all_categories).drop(columns="parent_category")
  df_cat_resolved.to_csv(os.path.join(args["outdir"], categories_out_file), sep='\t', float_format="%.0f", index=False)
  return df_cat_resolved

#############################################################################################
# Listing preprocessing functions
#############################################################################################

def determineParentCategories(df_cat, cid):
  '''Determines for a product category (cid) all parents in the hierarchy of product categories
  Parameters:
    df_cat - dataframe storing already resolved market product category information
    cid    - market product category identifier for which parent categories are meant to be determined
  '''
  new_parents = set(df_cat.loc[df_cat["cid"] == cid]["parent_cid"].unique())
  all_parents = new_parents.copy()
  while len(new_parents) > 0:
    parents = set()
    for parent in new_parents:
      parents.update(df_cat.loc[df_cat["cid"] == parent]["parent_cid"].unique())
    new_parents = parents
    all_parents.update(new_parents)
  return all_parents

def resolveListingVendorConflicts(dfus, warning_info):
  '''Checks if there are any remaining vendor conflicts for the same listing identifier.
     Should already been fixed when fixing the known issues with "fixKnownExtractionIssuesInListingDataframe()" earlier.
  Parameters
    dfus         - List of panda dataframes within which the variable must be checked for conflicts
    warning_info - String used in warnings to identify the exact instance for which the warning occurs
  Returns: market vendor identifier associated with the listing under consideration

  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu["vid"].unique())
  var_set = {x for x in var_set if x == x and x != ''}

  if len(var_set) > 1: # Warn of vendor conflicts, which should not be occurring anymore
    print("Warning (11): Multiple vendors known for {}. Options are {}.".format(warning_info, var_set))
    return list(var_set)[0]
  elif len(var_set) == 1:
    return list(var_set)[0]
  else:
    return None

def getTitlesDict(all_titles):
  '''Identify the title options that are simply a substring of another and thus not different products
  Parameters:
    all_titles - list of all titles extracted for a given market listing and scrape
  Returns: a dictionary of titles, with keys all titles that are NOT a substring of another and
           all substrings added to the set value of the superstring key
  '''
  sorted_titles = sorted(all_titles, key=len, reverse=True)
  titles_dict = {sorted_titles[0]:set([sorted_titles[0]])}

  for title in sorted_titles[1:]:
    titles_dict_copy = titles_dict.copy()
    for title_key, title_set in titles_dict_copy.items():
      if title.lower() in title_key.lower():
        title_set.add(title)
      else:
        titles_dict[title] = set([title])

  return titles_dict

def resolveListingConflicts(dfus, info, var, warning_info, df_cat=None):
  ''' Determines whether there are any conflicts for a given variable and (if known) resolves them
      by choosing the option with the 'latest' retrieval time
  Parameters:
    dfus         - List of panda dataframes within which the variable must be checked for conflicts
    info         - Dictionary in which the resolved variable must be stored
    var          - Variable (string) for which conflicts must be checked
    warning_info - String used in warnings to identify the exact instance for which the warning occurs
    df_cat       - dataframe storing already resolved market product category information (only necessary with var == cid)
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set = set()
  for dfu in dfus:
    var_set.update(dfu[var].unique())
  var_set = {x for x in var_set if x == x and x != ''}
  if len(var_set) > 1:
    if var == "cid":
      # If multiple category id's possible, choose the child option (i.e., the most specific option)
      remove_parents = set()
      for option in var_set:
        remove_parents.update(determineParentCategories(df_cat, option))
      for parent in remove_parents:
        if parent in var_set:
          var_set.remove(parent)
      # Check if only 1 option left
      if len(var_set) == 1:
        info[var] =list(var_set)[0]
        return
    # Still more than 1 option left. Choose based on retrieval time
    var_options = pd.concat([dfu.loc[dfu[var].isin(var_set)][[var, "retrieval_time"]] for dfu in dfus], ignore_index=True).dropna().drop_duplicates().sort_values(["retrieval_time"], ascending=[False]).reset_index(drop=True)
    info[var] = var_options[var][0]
    # Price naturally is subject to change due to being a Bitcoin representation of normal currency value.
    if var not in ["price"]:#, "title", "cid", "product_class"]:
      # for dfu in dfus:
      #   for i in dfu.index:
      #     print(dfu.loc[i])
      print("Warning (3): Multiple {} information for {}. Options are {}. Last retrieved ({}) chosen.".format(var, warning_info, var_set, info[var]))


  elif len(var_set) == 1:
    info[var] = list(var_set)[0]
  elif var not in ["description", "store_description", "cid", "ships_from", "ships_to", "product_class", "listing_available", "return_policy", "error"]: # These types of information can often be missing as they are only included in certain files, which may not always have been retrieved
    if info["error"] != 3: # On error 3 any information may be missing
      print("Warning (4): Missing {} information for {}".format(var, warning_info))

def fixKnownExtractionIssuesInListingDataframe(df):
  """ On several occasions, due to vid conflicts we could observe the incorrect listing identifier
      being associated with a listing on store/category pages. We fix these known cases here.
  Parameters:
    df - the dataframe wherein the issues need to be fixed
  """
  # One too low cases
  df.loc[(df["lid"] == 53570) & (df["vid"] == 22385), "lid"] = 53571
  df.loc[(df["lid"] == 65763) & (df["vid"] == 62536), "lid"] = 65764
  df.loc[(df["lid"] == 77745) & (df["vid"] == 174142), "lid"] = 77746
  df.loc[(df["lid"] == 84399) & (df["vid"] == 187024), "lid"] = 84400
  df.loc[(df["lid"] == 88554) & (df["vid"] == 173439), "lid"] = 88555
  df.loc[(df["lid"] == 90865) & (df["vid"] == 157138), "lid"] = 90866

  df.loc[(df["lid"] == 10463) & (df["title"] == "30mg Adderall IR"), "lid"] = 10464
  # One too high cases
  df.loc[(df["lid"] == 18398) & (df["vid"] == 21211), "lid"] = 18397
  df.loc[(df["lid"] == 61346) & (df["vid"] == 18173), "lid"] = 61345
  df.loc[(df["lid"] == 85432) & (df["vid"] == 110564), "lid"] = 85431
  df.loc[(df["lid"] == 92497) & (df["vid"] == 148490), "lid"] = 92496
  df.loc[(df["lid"] == 101684) & (df["vid"] == 211154), "lid"] = 101683

  # Somehow they got mixed up both ways, cases
  df.loc[(df["lid"] == 73947) & (df["vid"] == 10127), "lid"] = 73948
  df.loc[(df["lid"] == 73948) & (df["vid"] == 160704), "lid"] = 73947

  df.loc[(df["lid"] == 75403) & (df["vid"] == 224513), "lid"] = 75404
  df.loc[(df["lid"] == 75404) & (df["vid"] == 127372), "lid"] = 75403

  df.loc[(df["lid"] == 80064) & (df["vid"] == 18932), "lid"] = 80065
  df.loc[(df["lid"] == 80065) & (df["vid"] == 58001), "lid"] = 80064

  df.loc[(df["lid"] == 90663) & (df["vid"] == 365359), "lid"] = 90664
  df.loc[(df["lid"] == 90664) & (df["vid"] == 142379), "lid"] = 90663

  df.loc[(df["lid"] == 98483) & (df["vid"] == 371694), "lid"] = 98484
  df.loc[(df["lid"] == 98484) & (df["vid"] == 220496), "lid"] = 98483

  df.loc[(df["lid"] == 102456) & (df["vid"] == 376151), "lid"] = 102457
  df.loc[(df["lid"] == 102457) & (df["vid"] == 380093), "lid"] = 102456

def preprocessListings(args, df_vendors, df_cat_resolved):
  '''Preprocess market listing data by combining extracted data on them and resolving any conflicts.
  Parameters:
    args            - dictionary of command line arguments given
    df_vendors      - dataframe storing already resolved market vendor information
    df_cat_resolved - dataframe storing already resolved market product category information
  Returns: a dataframe with combined and resolved market vendor information
  '''
  known_vids = set(df_vendors["vid"].unique())
  list_columns = ["lid", "vid", "scrape_id", "title", "price", "description", "listing_available", "ships_from", "ships_to",
                  "product_class", "cid", "retrieval_time", "error"]
  df_list = pd.read_csv(os.path.join(args["indir"], listings_file), sep="\t", index_col=False, usecols=list_columns)
  fb_columns = ["lid", "vid", "scrape_id", "title", "price", "listing_available", "ships_from",
                "product_class", "cid", "retrieval_time", "error"]
  df_fb   = pd.read_csv(os.path.join(args["indir"], feedback_listings_file), sep="\t", index_col=False, usecols=fb_columns)
  rp_columns = ["lid", "vid", "scrape_id", "title", "price", "listing_available", "ships_from",
                "product_class", "cid", "return_policy", "retrieval_time", "error"]
  df_rp   = pd.read_csv(os.path.join(args["indir"], rp_listings_file), sep="\t", index_col=False, usecols=rp_columns)

  cat_store_columns = ["lid", "vid", "scrape_id", "title", "price", "store_description", "product_class", "cid", "retrieval_time", "error"]
  df_cat = pd.read_csv(os.path.join(args["indir"], category_listings_file), sep="\t", index_col=False, usecols=cat_store_columns)
  df_store = pd.read_csv(os.path.join(args["indir"], store_listings_file), sep="\t", index_col=False, usecols=cat_store_columns)
  # Combine all data sources into a single dataframe
  df_merge = pd.concat([df_list, df_fb, df_rp, df_cat, df_store], ignore_index=True)
  # Fix known issues w.r.t. listing identifiers being off by one
  fixKnownExtractionIssuesInListingDataframe(df_merge)

  # Resolve market listing data for one listing identifier at a time
  all_listings = []
  for lid in sorted(df_merge["lid"].unique()):
    print("Now processing lid {}".format(lid), end='\r')
    dfl_merge = df_merge.loc[df_merge["lid"] == lid]

    vid = resolveListingVendorConflicts([dfl_merge], "lid = {}".format(lid))
    if vid is not None and vid not in known_vids:  # Check if vid known (should always be the case)
      print("Warning (6): Unknown vid detected for lid {}. vid = {}".format(lid, vid))

    # Preprocess for each scrape for which we have data separately
    for sid in sorted(dfl_merge["scrape_id"].unique()):
      dfls_merge = dfl_merge.loc[dfl_merge["scrape_id"] == sid]

      # Determine for each scrape the set of different titles indicating possibly different listings
      titles = [x for x in dfls_merge["title"].unique() if x == x and x != '']
      if len(titles) == 0: # does not occur
        print("Warning (16): No titles found for lid {}, sid {}. Scrape skipped.".format(lid, sid))
        continue
      titles_dict = getTitlesDict(titles)
      if len(titles_dict) > 1:
        print("Warning (17): Multiple non-substring titles detected for lid {}, sid {} with titles_dict = {}".format(lid, sid, titles_dict))

      # Resolve listing information for each separate (non-substring) title as these can indicate different products
      for title, title_set in titles_dict.items():
        listing_info = {"lid":lid, "vid":vid, "mscrape_id":sid,
                        "title":title, "price":None, "description":None, "cid":None,
                        "ships_from":None, "ships_to":None, "product_class":None,
                        "listing_available":None, "return_policy":None, "error":None}

        dflst_merge = dfls_merge.loc[dfls_merge["title"].isin(title_set)]
        warning_info = "lid {}, sid {}".format(lid, sid)

        resolveListingConflicts([dflst_merge], listing_info, "error", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "price", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "description", warning_info)
        # If there is no description of the listing, we check if there is a store description
        # (which is usually the first few lines of the full description)
        if listing_info["description"] is None:
          descr_info = {"store_description":None}
          resolveListingConflicts([dflst_merge], descr_info, "store_description", warning_info)
          if descr_info["store_description"] is not None:
            listing_info["description"] = descr_info["store_description"]
        resolveListingConflicts([dflst_merge], listing_info, "cid", warning_info, df_cat_resolved)
        resolveListingConflicts([dflst_merge], listing_info, "ships_from", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "ships_to", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "product_class", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "listing_available", warning_info)
        resolveListingConflicts([dflst_merge], listing_info, "return_policy", warning_info)

        all_listings.append(listing_info)

  # Store the resolved market listings data. The error information is dropped for the final dataset
  df_merged_listings = pd.DataFrame(all_listings).drop(columns="error")
  df_merged_listings["price"] = df_merged_listings["price"].map(lambda x: '{0:.4f}'.format(x))
  df_merged_listings.to_csv(os.path.join(args["outdir"], listings_out_file), sep='\t', float_format="%.0f", index=False)

#############################################################################################
# Vendor preprocessing functions
#############################################################################################

def splitRankSales(combined, warning_info):
  '''Splits the string indicating the vendor rank into the actual rank and the sales components and returns those
  Parameters:
    combined     - string of the vendor rank giving information on both the rank and number of sales
    warning_info - warning message to be displayed in case such a warning is applicable
  Returns: the rank and number of sales defined by 'combined'

  '''
  if combined in early_rank_order:
    return combined, None
  else:
    split = combined.split(" ( ")
    if len(split) == 2:
      return split[0], int(split[1][:-2])
    else:
      print("Error (3): Unexpected rank format for {}: rank = {}".format(warning_info, combined))
      return None, None

def resolveUsernameVendorConflicts(dfus, warning_info):
  '''Resolve vendor username conflicts for the same vid. Choice at conflict based on manual choice made.
  Parameters:
    dfus         - list of dataframes with information on a specific vid, which may include multiple username options
    warning_info - warning message to be displayed in case such a warning is applicable
  '''
  var_set_complete = set()
  for dfu in dfus:
    var_set_complete.update(dfu["username"].unique())
  var_set = {x for x in var_set_complete if x == x and x != ''}

  if "only_bak" in var_set:
    return "only"
  elif "ShadyTom" in var_set:
    return "Luxor"
  elif "NOT_utopic" in var_set:
    return "utopic"
  elif "NOT_UKWHITE" in var_set:
    return "UKWHITE"
  elif "Addyshack" in var_set:  # Though both have a matching forum user, only Phaethon has any posts
    return "Phaethon"
  elif "thunderwiz" in var_set:
    return "ThunderWiz"
  elif "sargon" in var_set:
    return "Sargon"
  elif len(var_set) > 2: # If multiple options, but not yet manual choice made
    print("Warning (0): Multiple usernames for {}. Options are {}.".format(warning_info, var_set))
    return list(var_set)[0]
  elif len(var_set) == 1:
    return list(var_set)[0]
  else:
    return None

def resolveVendorConflicts(dfus, info, var, warning_info):
  ''' Determines whether there are any conflicts for a given variable and (if known) resolves them
      by choosing the option with the 'latest' retrieval time
      Note: this function expects the var "disabled" to be have been resolved first. Furthermore, the var "error"
      is expected to be resolved before "rank", "positive_feedback", "neutral_feedback", and "negative_feedback"!
  Parameters:
    dfus         - List of panda dataframes within which the variable must be checked for conflicts
    info         - Dictionary in which the resolved variable must be stored
    var          - Variable (string) for which conflicts must be checked
    warning_info - String used in warnings to identify the exact instance for which the warning occurs
  Post: Either the resolved variable is set into the dictionary or an error is output for a previously unknown conflict
  '''
  var_set_complete = set()
  for dfu in dfus:
    var_set_complete.update(dfu[var].unique())
  var_set = {x for x in var_set_complete if x == x and x != ''}

  if len(var_set) > 1:
    var_options = pd.concat([dfu[[var, "retrieval_time"]] for dfu in dfus], ignore_index=True).drop_duplicates().replace('', pd.NA).dropna().sort_values(["retrieval_time"], ascending=[False]).reset_index(drop=True)
    if var == "rank":
      info["rank"], info["sales"] = splitRankSales(var_options[var][0], warning_info)
    else:
      info[var] = var_options[var][0]
      # Rank, approval_rating and feedback statistics are naturally subject to change, and in case of disabled it only changes
      # from False to True, so for each of these using the latest information is a foregone conclusion
      if var not in ["rank", "positive_feedback", "neutral_feedback", "negative_feedback", "approval_rating", "disabled"]:
        print("Warning (1): Multiple {} information for {}. Options are {}. Last retrieved ({}) chosen.".format(var, warning_info, var_set, info[var]))
  elif len(var_set) == 1:
    if var == "rank":
      info["rank"], info["sales"] = splitRankSales(list(var_set)[0], warning_info)
    else:
      info[var] = list(var_set)[0]
  elif not info["disabled"]: # For disabled accounts we do not expect to be able to obtain any profile information.
    if info["error"] != '3': # On error 3 any number of information types can be missing
      if var not in ["legacy_sales", "pgp_key", "return_policy", "error"]: # Ignore fields that are likely to be empty often anyway, due to them being retrieved from specific files which may or may not have been available
        if not (var in ["rank", "positive_feedback", "neutral_feedback", "negative_feedback"] and info["error"] in ['3', '8']): # On error 8 we do not expect to have been able to retrieve this information
          if not (var == "approval_rating" and np.isnan(list(var_set_complete)[0])): # If there was no feedback yet, approval_rating was set to 'nan'
            print("Warning (2): Missing {} information for {} with error {}, with var_set_complete = {}".format(var, warning_info, info["error"], var_set_complete))

def preprocessVendors(args):
  '''Preprocess market vendor data by combining extracted data on them and resolving any conflicts.
  Parameters:
    args - dictionary of command line arguments given
  Returns: a dataframe with combined and resolved market vendor information
  '''
  # We start by reading in all relevant extracted vendor data, combining the various listing sources into one dataframe
  relevant_columns = ["vid", "username", "rank", "approval_rating", "scrape_id", "retrieval_time"]
  df_main = pd.read_csv(os.path.join(args["indir"], listings_file), sep="\t", index_col=False, usecols=relevant_columns)
  df_fb   = pd.read_csv(os.path.join(args["indir"], feedback_listings_file), sep="\t", index_col=False, usecols=relevant_columns)
  df_rp   = pd.read_csv(os.path.join(args["indir"], rp_listings_file), sep="\t", index_col=False, usecols=relevant_columns)
  df_cat  = pd.read_csv(os.path.join(args["indir"], category_listings_file), sep="\t", index_col=False, usecols=relevant_columns)
  df_st   = pd.read_csv(os.path.join(args["indir"], store_listings_file), sep="\t", index_col=False, usecols=relevant_columns)
  df_list = pd.concat([df_main, df_fb, df_rp, df_cat, df_st], ignore_index=True).drop_duplicates().sort_values(["vid", "scrape_id", "retrieval_time"], ascending=[True, True, True]).reset_index(drop=True)
  df_prof = pd.read_csv(os.path.join(args["indir"], profiles_file), sep="\t", index_col=False, keep_default_na=False).drop_duplicates()

  # Next we preprocess for one vid at a time
  all_vids = sorted([int(x) for x in set(df_list["vid"].unique()).union(set(df_prof["vid"])) if x == x])
  all_usernames = set(df_list["username"].unique()).union(set(df_prof["username"]))
  all_vendor_profiles = []
  for vid in all_vids:
    print("Now processing vid {}  ".format(vid), end="\r")
    dfv_list = df_list.loc[df_list["vid"] == vid]
    dfv_prof = df_prof.loc[df_prof["vid"] == vid]

    # Resolve vendor username and vid
    usn = resolveUsernameVendorConflicts([dfv_list, dfv_prof], "vid {}".format(vid))
    if usn is None:
      print("Warning (10): Missing username for vid {} and indeed no useful information available at all. Thus skipped.".format(vid))
      continue

    # Preprocess for each scrape for which we have data on this vendor separately
    relevant_scrapes = set(dfv_list["scrape_id"].unique()).union(set(dfv_prof["scrape_id"]))
    for sid in sorted(relevant_scrapes):
      vid_info = {"vid":vid, "mscrape_id":sid, "username":usn, "rank":None, "sales":None, "approval_rating":None,
                  "positive_feedback":None, "neutral_feedback":None, "negative_feedback":None,
                  "legacy_sales":None, "pgp_key":None, "return_policy":None, "disabled":None, "error":None}

      dfvs_list = dfv_list.loc[dfv_list["scrape_id"] == sid]
      dfvs_prof = dfv_prof.loc[dfv_prof["scrape_id"] == sid]

      warning_info = "vid {}, sid {}".format(vid, sid)
      # Check for errors first as errors indicate expected missing information, this informs warning decisions
      resolveVendorConflicts([dfvs_prof], vid_info, "error", warning_info)
      # Check for disabled next, for disabled accounts rarely show any other information
      if len(dfvs_prof) > 0:  # If there is no profile information there is also no disabled information
        resolveVendorConflicts([dfvs_prof], vid_info, "disabled", warning_info)
      resolveVendorConflicts([dfvs_list, dfvs_prof], vid_info, "rank", warning_info)
      if len(dfvs_prof) > 0:  # If there is no profile information there are also no feedback statistics, nor information like legacy_sales, pgp_key, or (vendor wide) return_policy
        resolveVendorConflicts([dfvs_prof], vid_info, "positive_feedback", warning_info)
        resolveVendorConflicts([dfvs_prof], vid_info, "neutral_feedback", warning_info)
        resolveVendorConflicts([dfvs_prof], vid_info, "negative_feedback", warning_info)

        resolveVendorConflicts([dfvs_prof], vid_info, "legacy_sales", warning_info)
        resolveVendorConflicts([dfvs_prof], vid_info, "pgp_key", warning_info)
        resolveVendorConflicts([dfvs_prof], vid_info, "return_policy", warning_info)
      if len(dfvs_list) > 0:  # If there is no listing information there is also no approval_rating information
        resolveVendorConflicts([dfvs_list], vid_info, "approval_rating", warning_info)

      all_vendor_profiles.append(vid_info)

  # If there are any vendor usernames not yet covered by a vid and are not ones explicitly not chosen on username conflict,
  # create new vid for them and resolve their data
  df_temp = pd.DataFrame(all_vendor_profiles)
  covered_usernames = df_temp["username"].unique()
  non_covered_usernames = [username for username in all_usernames if username not in covered_usernames and username == username and username != '' and username not in ["only_bak", "ShadyTom", "NOT_utopic", "NOT_UKWHITE", "Addyshack", "thunderwiz", "sargon"]]
  max_vid = max(all_vids)
  for username in non_covered_usernames: # In practice, no usernames were not already covered thus this code is useless
    print("Now processing vendor username {}    ".format(username), end='\r')
    dfu_list = df_list.loc[df_list["username"] == username]
    dfu_prof = df_prof.loc[df_prof["username"] == username]

    # Preprocess for each scrape for which we have data on this vendor separately
    relevant_scrapes = set(dfu_list["scrape_id"].unique()).union(set(dfu_prof["scrape_id"]))
    max_vid += 1
    for sid in sorted(relevant_scrapes):
      vid_info = {"vid":max_vid, "mscrape_id":sid, "username":username, "rank":None, "sales":None, "approval_rating":None,
                  "positive_feedback":None, "neutral_feedback":None, "negative_feedback":None,
                  "legacy_sales":None, "pgp_key":None, "return_policy":None, "disabled":None, "error":None}

      dfus_list = dfu_list.loc[dfu_list["scrape_id"] == sid]
      dfus_prof = dfu_prof.loc[dfu_prof["scrape_id"] == sid]

      warning_info = "username {}, sid {}".format(username, sid)
      # Check for errors first as errors indicate expected missing information, this informs warning decisions
      resolveVendorConflicts([dfus_prof], vid_info, "error", warning_info)
      # Check for disabled next, for disabled accounts rarely show any other information
      if len(dfvs_prof) > 0:  # If there is no profile information there is also no disabled information
        resolveVendorConflicts([dfus_prof], vid_info, "disabled", warning_info)
      resolveVendorConflicts([dfus_list, dfvs_prof], vid_info, "rank", warning_info)
      if len(dfvs_prof) > 0:  # If there is no profile information there are also no feedback statistics, nor information like legacy_sales, pgp_key, or (vendor wide) return_policy
        resolveVendorConflicts([dfus_prof], vid_info, "positive_feedback", warning_info)
        resolveVendorConflicts([dfus_prof], vid_info, "neutral_feedback", warning_info)
        resolveVendorConflicts([dfus_prof], vid_info, "negative_feedback", warning_info)

        resolveVendorConflicts([dfus_prof], vid_info, "legacy_sales", warning_info)
        resolveVendorConflicts([dfus_prof], vid_info, "pgp_key", warning_info)
        resolveVendorConflicts([dfus_prof], vid_info, "return_policy", warning_info)
      if len(dfus_prof) > 0:  # If there is no listing information there is also no approval_rating information
        resolveVendorConflicts([dfus_prof], vid_info, "approval_rating", warning_info)

      all_vendor_profiles.append(vid_info)

  # Store and return a dataframe with the resolved market vendor data. The error information is dropped for the final dataset
  df_vendor_profiles = pd.DataFrame(all_vendor_profiles).drop(columns="error")
  df_vendor_profiles["approval_rating"] = df_vendor_profiles["approval_rating"].map(lambda x: '{0:.1f}'.format(x))
  df_vendor_profiles["approval_rating"] = df_vendor_profiles["approval_rating"].replace('nan', np.nan)
  df_vendor_profiles.to_csv(os.path.join(args["outdir"], profiles_out_file), sep='\t', float_format="%.0f", index=False)

  return df_vendor_profiles

#############################################################################################
# User match functions
#############################################################################################

def matchUsersMarketWithFora(args, df_vendors):
  '''Matches forum users to market vendors based on their usernames
  Parameters:
    args       - dictionary of command line arguments given
    df_vendors - dataframe storing already resolved market vendor information
  '''
  # Retrieve all uid, username and vid, username combinations of the forum users and market vendors
  df_forum_users = pd.read_csv(os.path.join(args["outdir"], forum_profile_file), sep="\t", index_col=False)[["uid", "username"]].drop_duplicates()
  df_market_users = df_vendors[["vid", "username"]].dropna().drop_duplicates()

  # Match forum users and market vendors based on username
  df_matched = pd.merge(df_forum_users, df_market_users, on=["username"], how="outer")
  df_matches = df_matched.dropna().copy()
  df_non_matches = df_matched[df_matched["uid"].isna() | df_matched["vid"].isna()]

  # Assign a match_id to each username that has a successful match
  df_matches["match_id"] = pd.factorize(df_matches["username"])[0]
  df_matched.at[df_matches.index, "match_id"] = df_matches["match_id"]

  # Output some statistics
  print("Number of unique forum usernames: {}\nNumber of unique market usernames: {}\nNumber of market usernames with a matching forum username: {}".format(len(df_forum_users["username"].unique()), len(df_market_users["username"].unique()), len(df_matches["username"].unique())))

  # Store the matched forum user and market vendor data
  df_matched = df_matched.sort_values(["match_id", "username", "uid", "vid"], ascending=[True, True, True, True])
  df_matched.to_csv(os.path.join(args["outdir"], market_forum_user_matching_file), sep='\t', float_format="%.0f",
                    columns=["match_id", "username", "uid", "vid"], index=False)

#############################################################################################
# Feedback preprocessing function
#############################################################################################

def preprocessFeedback(args):
  '''Preprocess feedback data by simply removing duplicates. No further preprocessing is performed
  Parameters:
    args - dictionary of command line arguments given
  '''
  fb_columns = ["lid", "username", "year", "month", "day", "message"]
  df_feedback = pd.read_csv(os.path.join(args["indir"], feedback_file), sep="\t", index_col=False, usecols=fb_columns)
  df_feedback = df_feedback.drop_duplicates().sort_values(["lid", "year", "month", "day"], ascending=[True, True, True, True])
  df_feedback.to_csv(os.path.join(args["outdir"], feedback_out_file), sep="\t", float_format="%.0f",
                     columns=fb_columns, index=False)

#############################################################################################
# Scrape preprocessing function
#############################################################################################

def preprocessScrapes(args):
  '''Copies the scrape table from extraction directory to output directory after renaming one column
  Parameters:
    args - dictionary of command line arguments given
  '''
  df_scrape = pd.read_csv(os.path.join(args["indir"], scrapes_file_market), sep='\t', index_col=False)
  df_scrape.columns = ["mscrape_id", "scrape_year", "scrape_month", "scrape_day"]
  df_scrape.to_csv(os.path.join(args["outdir"], scrapes_file), sep='\t', float_format="%.0f", index=False)

#############################################################################################
# Main function
#############################################################################################

if __name__ == "__main__":
  sys.stdout = Logger()
  start_time = timeit.default_timer()

  # Process command line input to obtain input and output base directories
  input_parser = InputParser()
  args = input_parser.getInputArgumentsAsDict()
  os.makedirs(os.path.join(args["outdir"], "market"), exist_ok=True)
  os.makedirs(os.path.join(args["outdir"], "forum-market"), exist_ok=True)

  # Resolve scrape data
  preprocessScrapes(args)
  # Resolve vendor data and match vendors to forum users
  df_vendors = preprocessVendors(args)
  matchUsersMarketWithFora(args, df_vendors)
  # Resolve category and listing data
  df_cat_resolved = resolveCategories(args)
  preprocessListings(args, df_vendors, df_cat_resolved)
  # Simple feedback pre-processing (i.e., simple removing of duplicates)
  preprocessFeedback(args)

  stop_time = timeit.default_timer()
  print("Total runtime: {}s".format(stop_time - start_time))
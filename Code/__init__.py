import datetime, re, time, unicodedata, hashlib, urlparse, types, urllib, sys
from settings import *
## from Allocine import Allocine
## from Movie import Movie
## from Person import Person
## from Review import Review


# [might want to look into language/country stuff at some point] 
# param info here: http://code.google.com/apis/ajaxsearch/documentation/reference.html
#
GOOGLE_JSON_URL = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&userip=%s&rsz=large&q=%s'
FREEBASE_URL    = 'http://freebase.plexapp.com'
FREEBASE_BASE   = 'movies'
PLEXMOVIE_URL   = 'http://plexmovie.plexapp.com'
PLEXMOVIE_BASE  = 'movie'

SCORE_THRESHOLD_IGNORE         = 85
SCORE_THRESHOLD_IGNORE_PENALTY = 100 - SCORE_THRESHOLD_IGNORE
SCORE_THRESHOLD_IGNORE_PCT = float(SCORE_THRESHOLD_IGNORE_PENALTY)/100
PERCENTAGE_BONUS_MAX = 20

def Start():
  HTTP.CacheTime = CACHE_1HOUR * 4
  
class PlexMovieAgent(Agent.Movies):
  name = 'Allocine'
  languages = [Locale.Language.French]
  primary_provider = True

  def identifierize(self, string):
      string = re.sub( r"\s+", " ", string.strip())
      string = unicodedata.normalize('NFKD', safe_unicode(string))
      string = re.sub(r"['\"!?@#$&%^*\(\)_+\.,;:/]","", string)
      string = re.sub(r"[_ ]+","_", string)
      string = string.strip('_')
      return string.strip().lower()

  def guidize(self, string):
    hash = hashlib.sha1()
    hash.update(string.encode('utf-8'))
    return hash.hexdigest()

  def titleyear_guid(self, title, year):
    if title is None:
      title = ''

    if year == '' or year is None or not year:
      string = "%s" % self.identifierize(title)
    else:
      string = "%s_%s" % (self.identifierize(title).lower(), year)
    return self.guidize("%s" % string)
  
  def getPublicIP(self):
    ip = HTTP.Request('http://plexapp.com/ip.php').content.strip()
    return ip
  
  def getGoogleResults(self, url):
    try:
      jsonObj = JSON.ObjectFromURL(url, sleep=0.5)
      
      if jsonObj['responseData'] != None:
        jsonObj = jsonObj['responseData']['results']
        if len(jsonObj) > 0:
          return jsonObj
    except:
      Log("Exception obtaining result from Google.")
    
    return []

  
  def search(self, results, media, lang, manual=False):
    
    # Log Fred
    Log("*** AlloCine *** search")
    
    # Keep track of best name.
    lockedNameMap = {}
    resultMap = {}
    idMap = {}
    bestNameMap = {}
    bestNameDist = 1000
    bestHitScore = 0
    
    # TODO: create a plex controlled cache for lookup
    # TODO: by imdbid  -> (title,year)
    # See if we're being passed a raw ID.
    findByIdCalled = False
    
    # Log Fred
    Log("media.guid : %s, media.name : %s" % (media.guid, media.name))
    
    if media.year:
      searchYear = u' (' + safe_unicode(media.year) + u')'
    else:
      searchYear = u''
      
    # first look in the proxy/cache 
    titleyear_guid = self.titleyear_guid(media.name,media.year)
    
    Log("media.year : %s, titleyear_guid : %s" % (media.year, titleyear_guid))
    
    cacheConsulted = False
    
    score = 100
    
    url = "http://api.allocine.fr/rest/v3/search?partner=%s&format=json&filter=movie&q=%s&count=%s" % (PARTNER_CODE, urllib.quote_plus(media.name), 500)
    try:
        jsonAlloCine = JSON.ObjectFromURL(url, sleep=0.5)
        Log("Checking on Allocine with url: %s" % url)
        if jsonAlloCine.get("feed") != None:
            feed = jsonAlloCine.get("feed")
            #Log("feed : %s" % feed)
            
            for movie in feed.get("movie"):
                #Log("Movie feed : %s" % movie)
                id = str(movie.get("code"))
                
                imdbName = ""
                originalImdbName = ""
                try: originalImdbName = str(safe_unicode(movie.get("originalTitle")))
                except: pass
                
                try: imdbName = str(safe_unicode(movie.get("title")))
                except: imdbName = originalImdbName
                
                try: imdbYear = int(movie.get("productionYear"))
                except:
                    try:
                        for release in movie.get("release"):
                            releaseDate = release.get("releaseDate")
                            imdbYear = int(releaseDate[0:4])
                    except: pass
                        
                
                lang=str("fr")
                try:
                   for language in movie.get("language"):
                       lang = language.get("$")
                except: pass
                
                Log("Movie - code: %s, release : %s, Title : %s, OriginalTitle : %s" % (id, imdbYear, imdbName, originalImdbName))
                
                # First try with the Title afterwards with originalTitle if matching score is not high enough
                distance = Util.LevenshteinDistance(media.name, imdbName.encode('utf-8'))
                Log("distance for %s: %s" % (imdbName, distance))
                
                bestNameMap[id] = imdbName
                bestNameDist = distance
                scorePenalty = int(distance*2)
                
                if int(imdbYear) > datetime.datetime.now().year:
                   Log(imdbName + ' penalizing for future release date')
                   scorePenalty += SCORE_THRESHOLD_IGNORE_PENALTY 
                   
                # Check to see if the hinted year is different from imdb's year, if so penalize.
                elif media.year and imdbYear and int(media.year) != int(imdbYear):
                   Log('%s penalizing for hint year (%s) and imdb year (%s) being different' % (imdbName, int(media.year), int(imdbYear)))
                   yearDiff = abs(int(media.year)-(int(imdbYear)))
                   if yearDiff == 1:
                      scorePenalty += 5
                   elif yearDiff == 2:
                      scorePenalty += 10
                   else:
                      scorePenalty += 15
                # Bonus (or negatively penalize) for year match.
                #elif media.year and imdbYear and int(media.year) == int(imdbYear):
                #   scorePenalty += -5
                
                Log("score penalty (used to determine if google is needed) = %d (score %d)" % (scorePenalty, score))
                
                # Perhaps is originalTitle a beter match
                if imdbName != originalImdbName:
                    distance = Util.LevenshteinDistance(media.name, originalImdbName.encode('utf-8'))
                    Log("distance for %s: %s" % (originalImdbName, distance))
                    
                    scorePenaltyOrig = int(distance*2)
                    
                    if int(imdbYear) > datetime.datetime.now().year:
                       Log(originalImdbName + ' penalizing for future release date')
                       scorePenaltyOrig += SCORE_THRESHOLD_IGNORE_PENALTY 
                    
                    # Check to see if the hinted year is different from imdb's year, if so penalize.
                    elif media.year and imdbYear and int(media.year) != int(imdbYear):
                       Log('%s penalizing for hint year (%s) and imdb year (%s) being different' % (originalImdbName, int(media.year), int(imdbYear)))
                       yearDiff = abs(int(media.year)-(int(imdbYear)))
                       if yearDiff == 1:
                          scorePenaltyOrig += 5
                       elif yearDiff == 2:
                          scorePenaltyOrig += 10
                       else:
                          scorePenaltyOrig += 15
                    
                # If originalTitle beter match than Title, we use originalTitle
                if (score - scorePenalty) < (score - scorePenaltyOrig):
                    scorePenalty = scorePenaltyOrig
                    imdbName = originalImdbName
                
                
                if (score - scorePenalty) > bestHitScore:
                   bestHitScore = score - scorePenalty               
                
                # Get the official, localized name.
#                name, year = get_best_name_and_year(id, lang, imdbName, imdbYear, lockedNameMap)
                cacheConsulted = True
                results.Append(MetadataSearchResult(id = id, name  = imdbName, year = int(imdbYear), lang  = lang, score = int(score-scorePenalty)))
                Log("Append MetadataSearcResult : id=%s, name=%s, year=%s, lang=%s, score=%d" % (id, imdbName, int(imdbYear), lang, int(score - scorePenalty)))
                score = score - 4
                
        else:
            Log("No result found on Allocine for : %s" % media.title)
            setAlloCine = False
    except Exception, err:
        Log("Error searching for %s on AlloCine" % media.title)
        Log("Error : %s, line nr : %s", str(err), sys.exc_traceback.tb_lineno)
        setAllocine = False
        
        
    doGoogleSearch = False
    if len(results) == 0 or bestHitScore < SCORE_THRESHOLD_IGNORE or manual == True or (bestHitScore < 100 and len(results) == 1):
        doGoogleSearch = True
      
    Log("PLEXMOVIE INFO RETRIEVAL: FINDBYID: %s CACHE: %s SEARCH_ENGINE: %s" % (findByIdCalled, cacheConsulted, doGoogleSearch))
    
    Log("Len(results)=%d, bestHitScore=%d, score_treshold_ignore=%d, manual=%s" % (len(results), bestHitScore, SCORE_THRESHOLD_IGNORE, manual))
    
    if doGoogleSearch:
      # Try to strip diacriticals, but otherwise use the UTF-8.
      normalizedName = String.StripDiacritics(media.name)
      if len(normalizedName) == 0:
        normalizedName = media.name
        
      GOOGLE_JSON_QUOTES =   GOOGLE_JSON_URL % (self.getPublicIP(), String.Quote(('"' + normalizedName + searchYear + '"').encode('utf-8'), usePlus=True)) + '+site:allocine.fr'
      GOOGLE_JSON_NOQUOTES = GOOGLE_JSON_URL % (self.getPublicIP(), String.Quote((normalizedName + searchYear).encode('utf-8'), usePlus=True)) + '+site:allocine.fr'
      GOOGLE_JSON_NOSITE =   GOOGLE_JSON_URL % (self.getPublicIP(), String.Quote((normalizedName + searchYear).encode('utf-8'), usePlus=True)) + '+allocine.fr'
      
      subsequentSearchPenalty = 0
      
      notMovies = {}
      
      for s in [GOOGLE_JSON_QUOTES, GOOGLE_JSON_NOQUOTES]:
        if s == GOOGLE_JSON_QUOTES and (media.name.count(' ') == 0 or media.name.count('&') > 0 or media.name.count(' and ') > 0):
          # no reason to run this test, plus it screwed up some searches
          continue 
          
        subsequentSearchPenalty += 1
        
        # Check to see if we need to bother running the subsequent searches
        Log("We have %d results" % len(results))
        if len(results) < 3 or manual == True:
          score = 99
          
          # Make sure we have results and normalize them.
          jsonObj = self.getGoogleResults(s)
            
          # Now walk through the results and gather information from title/url
          considerations = []
          for r in jsonObj:
            
            # Get data.
            url = safe_unicode(r['unescapedUrl'])
            title = safe_unicode(r['titleNoFormatting'])
            
            titleInfo = parseAlloCineTitle(title,url)
            if titleInfo is None:
              # Doesn't match, let's skip it.
              Log("Skipping strange title: " + title + " with URL " + url)
              continue
              
            imdbName  = titleInfo['title']
            imdbYear  = titleInfo['year']
            imdbId    = titleInfo['imdbId']
            imdbFiche = titleInfo['imdbFiche']
            
            Log("ParseAlloCineTitle result : imdbName=%s, imdbYear=%s, imdbID=%s, imdbFiche=%s" % (imdbName, imdbYear, imdbId, imdbFiche))
            
            if titleInfo['type'] != 'movie':
              notMovies[imdbId] = True
              Log("Title does not look like a movie: " + title + " : " + url)
              continue
              
            Log("Using [%s (%s)] derived from [%s] (url=%s)" % (imdbName, imdbYear, title, url))
              
            scorePenalty = 0
            url = r['unescapedUrl'].lower().replace('us.vdc','www').replace('title?','title/tt') #massage some of the weird url's google has
            
            (uscheme, uhost, upath, uparams, uquery, ufragment) = urlparse.urlparse(url)
            # strip trailing and leading slashes
            upath     = re.sub(r"/+$","",upath)
            upath     = re.sub(r"^/+","",upath)
            splitUrl  = upath.split("/")
            
            if splitUrl[-1] != imdbFiche:
              # This is the case where it is not just a link to the main imdb title page, but to a subpage. 
              # In some odd cases, google is a bit off so let's include these with lower scores "just in case".
              #
              Log("%s penalizing for not having correct Allocine fiche name at the end of url (splitUrl : %s, imdbFiche : %s)" % (imdbName, splitUrl[-1], imdbFiche))
              scorePenalty += 10
              del splitUrl[-1]
              
            if splitUrl[0] != 'film':
              # if the first part of the url is not the /title/... part, then
              # rank this down (eg www.imdb.com/r/tt_header_moreatpro/title/...)
              Log("%s penalizing for not starting with title (splitUrl[0] : %s" % (imdbName, splitUrl[0]))
              scorePenalty += 10
              
            if splitUrl[0] == 'r':
              Log(imdbName + " wierd redirect url skipping")
              continue
              
            for urlPart in reversed(splitUrl):  
              if urlPart == imdbFiche:
                break
              Log("%s penalizing for not at imdbid in url yet (urlPart : %s, rerversed(splitUrl) : %s" % (imdbName, urlPart, reversed(splitUrl)))
              scorePenalty += 5
              
            id = imdbId
            if id.count('+') > 0:
              # Penalizing for abnormal tt link.
              scorePenalty += 10
            try:
              # Keep the closest name around.
              distance = Util.LevenshteinDistance(media.name, imdbName.encode('utf-8'))
              Log("distance: %s" % distance)
              if not bestNameMap.has_key(id) or distance <= bestNameDist:
                bestNameMap[id] = imdbName
                if distance <= bestNameDist:
                  bestNameDist = distance
                  
              # Don't process for the same ID more than once.
              if idMap.has_key(id):
                continue
                
              # Check to see if the item's release year is in the future, if so penalize.
              if imdbYear > datetime.datetime.now().year:
                Log(imdbName + ' penalizing for future release date')
                scorePenalty += SCORE_THRESHOLD_IGNORE_PENALTY 
                
              # Check to see if the hinted year is different from imdb's year, if so penalize.
              elif media.year and imdbYear and int(media.year) != int(imdbYear): 
                Log(imdbName + ' penalizing for hint year and imdb year being different')
                yearDiff = abs(int(media.year)-(int(imdbYear)))
                if yearDiff == 1:
                  scorePenalty += 5
                elif yearDiff == 2:
                  scorePenalty += 10
                else:
                  scorePenalty += 15
                  
              # Bonus (or negatively penalize) for year match.
              #elif media.year and imdbYear and int(media.year) == int(imdbYear): 
              #  Log(imdbName + ' bonus for matching year')
              #  scorePenalty += -5
              
              # Sanity check to make sure we have SOME common substring.
              longestCommonSubstring = len(Util.LongestCommonSubstring(media.name.lower(), imdbName.lower()))
              
              # If we don't have at least 10% in common, then penalize below the 80 point threshold
              if (float(longestCommonSubstring) / len(media.name)) < SCORE_THRESHOLD_IGNORE_PCT: 
                Log(imdbName + ' terrible subtring match. skipping')
                scorePenalty += SCORE_THRESHOLD_IGNORE_PENALTY 
              
              # Finally, add the result.
              idMap[id] = True
              Log("score = %d" % (score - scorePenalty - subsequentSearchPenalty))
              titleInfo['score'] = score - scorePenalty - subsequentSearchPenalty
              considerations.append( titleInfo )
            except:
              Log('Exception processing IMDB Result')
              pass
              
            for c in considerations:
              if notMovies.has_key(c['imdbId']):
                Log("IMDBID %s was marked at one point as not a movie. skipping" % c['imdbId'])
                continue
                
              results.Append(MetadataSearchResult(id = c['imdbId'], name  = c['title'], year = c['year'], lang  = lang, score = c['score']))
              
            # Each search entry is worth less, but we subtract even if we don't use the entry...might need some thought.
            score = score - 4 
            
    ## end giant google block
    
    results.Sort('score', descending=True)
    
    # Finally, de-dupe the results.
    toWhack = []
    resultMap = {}
    for result in results:
      if not resultMap.has_key(result.id):
        resultMap[result.id] = True
      else:
        toWhack.append(result)
        
    for dupe in toWhack:
      results.Remove(dupe)
      
    # Make sure we're using the closest names.
    for result in results:
      if not lockedNameMap.has_key(result.id) and bestNameMap.has_key(result.id):
        Log("id=%s score=%s -> Best name being changed from %s to %s" % (result.id, result.score, result.name, bestNameMap[result.id]))
        result.name = bestNameMap[result.id]
        
  def update(self, metadata, media, lang, force):
  
    Log("*** AlloCine *** update")
    Log("*********>>>>>>>>>>>> Allocine <<<<<<<<<<<<***********")
    setAlloCine = True
    Log("Metadata : %s", metadata)
    
    setTitle = False
    if media and metadata.title is None:
      setTitle = True
      
    guid = re.findall('([0-9]+)', metadata.guid)[0]
    Log("guid findall : %s, metadata.guid : %s" % (guid, metadata.guid))
    url = "http://api.allocine.fr/rest/v3/movie?partner=%s&code=%s&profile=large&format=json&filter=movie&striptags=synopsis,synopsisshort"  % (PARTNER_CODE, guid)
    try:
        jsonAlloCine = JSON.ObjectFromURL(url, sleep=0.5)
        if jsonAlloCine.get("movie") != None:
            movie = jsonAlloCine.get("movie")
            #release = movie.get("release",[])
            #releaseDate = release.get("releaseDate", [])
            try:
                title = movie.get("title")
            except:
                title = movie.get("originalTitle")
            
            
            #Original_title
            metadata.original_title = movie.get("originalTitle")
            
            # Title.
            if setTitle:
                if title is not None:
                    metadata.title = title
            
            # Runtime
            try: metadata.duration = int(movie.get("runtime")) * 1000
            except: pass
            
            # Tagline
            try:
                metadata.tagline = ''
                i = 0
                for movie_tag in movie.get("tag"):
                    if i == 0:
                        metadata.tagline = movie_tag.get("$")
                        i = 1
                    else:
                        metadata.tagline = metadata.tagline + ', ' + movie_tag.get("$")
            except: pass
            
            # Genres
            try:
                metadata.genres.clear()
                for genre in movie.get("genre"):
                    metadata.genres.add(genre.get("$"))
            except: pass
            
            # Année
            try: metadata.year = int(movie.get("productionYear"))
            except:
                try:
                    for release in movie.get("release"):
                        releaseDate = release.get("releaseDate")
                        metadata.year = int(releaseDate[0:4])
                except:
                    pass
            
            # Summary
            try: metadata.summary = movie.get("synopsis")
            except: pass
            
            # Sort title
            try: metadata.title_sort = movie.get("originalTitle")
            except: pass
            
            # Rating
            try: 
                stat = movie.get("statistics")
                metadata.rating = stat.get("userRating") * 2
            except: pass
            
            # Directors, actors, writers, producers
            try:
                metadata.directors.clear()
                metadata.roles.clear()
                metadata.writers.clear()
                for cast in movie.get("castMember"):
                    activity = cast.get("activity")
                    code = int(activity.get("code"))
                    person = cast.get("person")
                    if code == 8001:
                        role = metadata.roles.new()
                        role.actor = person.get("name")
                        role.role = activity.get("$")
                    if code == 8002:
                        metadata.directors.add(person.get("name"))
                    if code == 8004:
                        metadata.writers.add(person.get("name"))
                    if code == 8029 or code == 8062:
                        metadata.writers.add(person.get("name"))
            except: pass
            
            # Country
            try:
                metadata.countries.clear()
                for country in movie.get("nationality"):
                    metadata.countries.add(country.get("$"))
            except: pass
            
            # Studio
            try:
                release = movie.get("release")
                i = 0
                studio = release.get("distributor")
                metadata.studio = studio.get("name")
            except: pass
            
            # Posters
            i = 0
            valid_names = list()
            try:
                poster = movie.get("poster")
                valid_names.append(poster["href"])
                if poster["href"] not in metadata.posters:
                    i += 1
                    thumb = HTTP.Request(poster["href"])
                    try: metadata.posters[poster["href"]] = Proxy.Preview(thumb, sort_order=i)
                    except: pass
            except: pass
            
            try:
                for media in movie.get("media"):
                    if media.get("class") == "picture":
                        picture = media.get("type", [])
                        if picture["$"] == "Affiche":
                            thumbnail = media.get("thumbnail")
                            valid_names.append(thumbnail["href"])
                            if thumbnail["href"] not in metadata.posters:
                                i += 1
                                thumb = HTTP.Request(thumbnail["href"])
                                try: metadata.posters[thumbnail["href"]] = Proxy.Preview(thumb, sort_order=i)
                                except: pass
            except: pass
            
            try: metadata.posters.validate_keys(valid_names)
            except: pass
            
            
            # Arts
            try:
                i = 0
                valid_names = list()
                for media in movie.get("media"):
                    if media.get("class") == "picture":
                        picture = media.get("type", [])
                        if picture["$"] == "Photo":
                            thumbnail = media.get("thumbnail")
                            valid_names.append(thumbnail["href"])
                            if thumbnail["href"] not in metadata.art:
                                i += 1
                                thumb = HTTP.Request(thumbnail["href"])
                                try: metadata.art[thumbnail["href"]] = Proxy.Preview(thumb, sort_order=i)
                                except: pass
            except:pass
            
            try: metadata.art.validate_keys(valid_names)
            except: pass
            
        else:
            Log("No result found on Allocine for : %s" % media.title)
            setAlloCine = False
    except Exception, err:
#        Log("Error searching for %s on AlloCine" % media.title)
        Log("Error : %s, line nr : %s", str(err), sys.exc_traceback.tb_lineno)
        
        setAllocine = False
        
    if not setAlloCine:
        m = re.search('([0-9]+)', metadata.guid)
        id = m.groups(1)[0]
        
        Log("Looking in Google for %s (id=%s, guid=%s)" % (media.title, id, metadata.guid))
        (title, year) = self.findById(id, skipFreebase=True)
        metadata.year = int(year)
        
        


  def findById(self, id, skipFreebase=False):
    title = None
    year = None
    
    Log("Avant GoogleResults")
	
    jsonObj = self.getGoogleResults(GOOGLE_JSON_URL % (self.getPublicIP(), id + '+site:allocine.fr'))
    
    Log("Apres Googleresults et avant le try")
    
    
    try:
    	Log("Dans le Try parse argument : %s, %s" % (jsonObj[0]['titleNoFormatting'],jsonObj[0]['unescapedUrl']))
    	
        titleInfo = parseAlloCineTitle(jsonObj[0]['titleNoFormatting'],jsonObj[0]['unescapedUrl'])
        
        Log("TitleInfo from Google : %s" % titleInfo)
        
        title = titleInfo['title']
        year = titleInfo['year']
    except:
        Log("Dans le Except!!!")
        pass

    if title and year:
      return (safe_unicode(title), safe_unicode(year))
    else:
      return (None, None)

def parseAlloCineTitle(title, url):

  titleLc = title.lower()

  result = {
    'title':  None,
    'year':   None,
    'type':   'movie',
    'imdbFiche': None,
    'imdbId': None
  }

  try:
    (scheme, host, path, params, query, fragment) = urlparse.urlparse(url)
    path      = re.sub(r"/+$","",path)
    pathParts = path.split("/")
    lastPathPart = pathParts[-1]
        
    Log("host : %s, pathParts : %s" % (host, pathParts))

    if host.count('allocine.') == 0:
       Log("Quitting ParseAlloCineTitle, allocine not finded in url : %s" % url)
       return None

    
    # parse the imdbId
    m=re.search('/(fichefilm_gen_cfilm=)([^0-9]+ )?([0-9]+)', path)
    imdbId = m.groups()[2]
    result['imdbId'] = imdbId
    
    Log("imdbID : %s" % imdbId)
    result['imdbFiche'] = lastPathPart
    Log("imdbFiche : %s" % result['imdbFiche'])
    
    # Parse out title, year, and extra.
    
    # titleRx = '(.*) \(([^0-9]+ )?([0-9]+)(/.*)?.*?\).*'
    titleRx = '(.*) - film ([^0-9]+ )?([0-9]+)(/.*)?.*? - .*'
    m = re.match(titleRx, title)
    
    Log("m : %s, title : %s" % (m.groups(), title))
        
    if m:
      # A bit more processing for the name.
      #result['title'] = cleanupIMDBName(m.groups()[0])
      result['title'] = m.groups()[0]
      result['year'] = int(m.groups()[2])
      
    else:
      # longTitleRx = '(.*\.\.\.)'
      # m = re.match(longTitleRx, title)
      #if m:
      #  result['title'] = cleanupIMDBName(m.groups(1)[0])
      #  result['year']  = None
      Log("Quitting ParseAllocineTitle, no ID finded, url :%s" % url)
      return None

    if result['title'] is None:
      Log("Quitting ParseAllocineTitle, title is not existing")
      return None

    return result
  except Exception, err:
    Log("Exception ParseAllocineTitle : url=%s" % url)
    Log("Error : %s" % str(err))
    return None
    

 
def cleanupIMDBName(s):
  imdbName = re.sub('^[aA][lL][lL][oO][cC][iI][nN][éE][ ]*:[ ]*', '', s)
  imdbName = re.sub('^details - ', '', imdbName)
  imdbName = re.sub('(.*:: )+', '', imdbName)
  imdbName = HTML.ElementFromString(imdbName).text

  if imdbName:
    if imdbName[0] == '"' and imdbName[-1] == '"':
      imdbName = imdbName[1:-1]
    return imdbName

  return None

def safe_unicode(s,encoding='utf-8'):
  if s is None:
    return None
  if isinstance(s, basestring):
    if isinstance(s, types.UnicodeType):
      return s
    else:
      return s.decode(encoding)
  else:
    return str(s).decode(encoding)
  
def get_best_name_and_year(guid, lang, fallback, fallback_year, best_name_map):
  url = '%s/%s/%s/%s.xml' % (FREEBASE_URL, FREEBASE_BASE, guid[-2:], guid)
  ret = (fallback, fallback_year)
  
  try:
    movie = XML.ElementFromURL(url, cacheTime=3600)
    
    movieEl = movie.xpath('//movie')[0]
    if movieEl.get('originally_available_at'):
      fallback_year = int(movieEl.get('originally_available_at').split('-')[0])

    lang_match = False
    if Prefs['title']:
      for movie in movie.xpath('//title'):
        if lang == movie.get('lang'):
          ret = (movie.get('title'), fallback_year)
          lang_match = True

    # Default to the English title.
    if not lang_match:
      ret = (movieEl.get('title'), fallback_year)
    
    # Note that we returned a pristine name.
    best_name_map['tt'+guid] = True
    return ret
      
  except:
    Log("Error getting best name.")

  return ret
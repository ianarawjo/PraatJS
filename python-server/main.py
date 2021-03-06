'''
    Web server interface to Praat scripts.

    @requires cherrypy.
    Database functions @require pymongo+MongoDB.

    TODO:
     - Refactor utils into separate module.
     - Refactor DB functions into separate module (SOCs).

    Created by ian on 12/23/15.
'''
# Server
import cherrypy
from cherrypy.lib.static import serve_file

# File I/O and processing
import tgt # TextGrid API
import subprocess
import tempfile
import os
import praatUtil
import math

# Database (you should be running mongod)
from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client['newspeak']
words_collection = db['words'] # DB is called 'newspeak' and Collection is called 'words'
user_collection = db['users'] # for safety reasons

constants = { 'SEGMENTS':40 }

# Computes the mean-squared-error between arbitrary graphs. (normalizes dx beforehand)
def mean_squared_error(A, B, abgn, aend, bbgn, bend):
    nA = mapToInterval(normalizeDx(A, 200), (abgn, aend), (0, 100))
    nB = mapToInterval(normalizeDx(B, 200), (bbgn, bend), (0, 100))
    meanA = computeMean(nA)
    meanB = computeMean(nB)
    nA = mapSubtractY(nA, meanA - 500)
    nB = mapSubtractY(nB, meanB - 500)
    return sum([((nA[i][1] - nB[i][1])**2) for i in xrange(200)]) / 200.0

# Calculates the area between two graphs
# of arbitrary x-distances between each point.
# > Does this by isolating the 'top graph' and the 'bottom graph'
# > based on their intersections, then subtracting the bottom area
# > from the top.
# < Takes: two lists of 2D tuples (x, y) representing graph A and B
# < NOTE: While dx can vary between points in A and B,
# < dx should be in the same ultimate range, i.e. 0.0 to 1.0 or 0 to 100,
# < and y should always be nonnegative (>= 0) for both A and B.
def areaBetween(A, B):
    if A == None or B == None or len(A) == 0 or len(B) == 0:
        return 0
    elif B[0][1] > A[0][1]: # enforce that A starts with highest Y-value
        return areaBetween(B, A)

    # Thanks to Paul Draper @ SO.
    # http://stackoverflow.com/a/20677983
    def findIntersection(line1, line2):

        # Thanks to Grumdrig @ SO.
        # http://stackoverflow.com/a/9997374
        def ccw(A,B,C):
            return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

        # Return true if line segments AB and CD intersect
        def intersect(A,B,C,D):
            return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)

        # First, determine whether SEGMENTS intersect...
        if intersect(line1[0], line1[1], line2[0], line2[1]) == False:
            return None

        # ...Then determine where.
        xdiff = (line1[0][0] - line1[1][0], line2[0][0] - line2[1][0])
        ydiff = (line1[0][1] - line1[1][1], line2[0][1] - line2[1][1])

        def det(a, b):
            return a[0] * b[1] - a[1] * b[0]

        div = det(xdiff, ydiff)
        if div == 0:
           return None

        d = (det(*line1), det(*line2))
        x = det(d, xdiff) / div
        y = det(d, ydiff) / div
        return (x, y)

    # Assumes all y's are >= 0...
    def areaUnder(X):
        area = 0
        for p in xrange(len(X)-1):
            x, y = X[p]
            nX, nY = X[p+1]
            dx = nX - x
            area += dx * abs(nY - y) / 2.0 + min(y, nY) * dx # area += dA
        return area

    # A starts high.
    top = []
    bottom = []
    j = 0
    for i in xrange(len(A)-1):
        aX, aY = A[i]
        naX, naY = A[i+1]
        bX, bY = B[j]
        nbX, nbY = B[j+1]
        while bX < aX and nbX < naX: # B's first point is behind us. Skip to the point where it's not.
            bottom.append(B[j])
            j += 1
            bX, bY = B[j]
            if j < len(B)-1: nbX, nbY = B[j+1]
            else:
                bottom.append(B[j])
                break

        if j >= len(B)-1:
            break

        # B's line starts after (or on) A's.
        inter = findIntersection((A[i], A[i+1]), (B[j], B[j+1]))
        if inter is None: # A's line is on top.
            top.append(A[i])
            continue
        else: # The lines intersect, and B comes out on top.
            # print((A[i], A[i+1], B[j], B[j+1], inter))
            top.append(A[i])
            top.append(inter)
            bottom.append(B[j])
            bottom.append(inter)
            nextBottom = list(A[(i+1):]).insert(0, inter) # A is now the underdog
            nextTop = list(B[(j+1):]).insert(0, (inter[0], inter[1]+0.00001)) # B's starting value must be slightly higher

            area_under_top = areaUnder(top)
            area_under_bot = areaUnder(bottom)
            print('Area under top: ' + str(area_under_top))
            print('Area under bottom: ' + str(area_under_bot))

            return areaUnder(top) - areaUnder(bottom) + areaBetween(nextTop, nextBottom) # yay tail recursion

    # We've reached the end of B.
    area_under_top = areaUnder(top)
    area_under_bot = areaUnder(bottom)
    print('Area under top: ' + str(area_under_top))
    print('Area under bottom: ' + str(area_under_bot))
    return areaUnder(top) - areaUnder(bottom)

def mapToInterval(A, originalInterval, newInterval):
    C = []
    oix, oix2 = originalInterval
    owidth = oix2 - oix
    nix, nix2 = newInterval
    nwidth = nix2 - nix
    for i in xrange(len(A)):
        x, y = A[i]
        ratio = (x - oix) / owidth
        if i == 0: C.append((nix, y))
        C.append((nix + ratio * nwidth, y))
    if len(C) > 0: C.append((nix2, C[-1][1]))
    return C
def toTupleList(A):
    C = []
    for i in xrange(len(A)):
        C.append((A[i][0], A[i][1]))
    return C
def mapSubtractY(A, mean):
    C = []
    for i in xrange(len(A)):
        C.append((A[i][0], A[i][1] - mean))
    return C

def eliminateNullPoints(X, Y):
    cX = []
    cY = []
    for i in xrange(len(X)):
        if X[i] > 0 or Y[i] > 0:
            cX.append(X[i])
            cY.append(Y[i])
    return (cX, cY)

def normalizeToUnitSquare(X, Y):

    # Normalize X and Y in range (0,1)
    end = X[-1]
    ymin = min(Y)
    yheight = max(Y) - ymin
    for i in xrange(len(X)):
        X[i] = X[i] / float(end)
        Y[i] = (Y[i] - ymin) / yheight

    # Normalize distance between points, so that dx is always constant.
    # * This makes it easier to compare two contours. *
    j = 0
    segs = constants.SEGMENTS
    nY = []
    for i in xrange(segs):
        x = i / float(segs)
        while j < len(X) and X[j] < x:
            j += 1
        # this is the point immediately 'before' X[j], bc X[j-1] < x and X[j] >= x...
        # (x - X[j]) / (X[j] - X[j-1])
        if j == 0:
            y = Y[j]
        else:
            dist = X[j] - X[j-1]
            a = (X[j] - x) / dist
            y = (1.0-a) * Y[j] + (a) * Y[j-1]
            print(X[j], x, X[j-1], '    ', a)

        nY.append(y)

    return nY

def normalizeDx(A, segs=100):

    X = [A[i][0] for i in xrange(len(A))]
    Y = [A[i][1] for i in xrange(len(A))]

    dur = X[-1] - X[0]

    # Normalize distance between points, so that dx is always constant.
    # * This makes it easier to compare two contours. *
    j = 0
    nA = []
    for i in xrange(segs):
        x = (i / float(segs)) * dur + X[0]
        while j < len(X) and X[j] < x:
            j += 1
        # this is the point immediately 'before' X[j], bc X[j-1] < x and X[j] >= x...
        # (x - X[j]) / (X[j] - X[j-1])
        if j == 0:
            y = Y[j]
        else:
            dist = X[j] - X[j-1]
            a = (X[j] - x) / dist
            y = (1.0 - a) * Y[j] + a * Y[j-1]

        nA.append((x, y))

    return nA

def convertAudioToWAV(wavfile, new_filename):
    cmd = ['ffmpeg', '-i', wavfile, new_filename]
    subprocess.call(cmd)

'''
    Handles database + audio cache on filesystem

    Metadata JSON format:
        { user: "...",
          word: "...",
          audio: "...", <link to resource>
          properties: {
            pitch: {
                contour: [...] <normalized y of points at equally spaced intervals, 0 to 1.0, scaled to 3 st deviations, where mean of points=0.5>
                avg: <float> (not normalized!)
                deviation: <float>
            },
            intensity: [...] <format same as pitch>
            duration: <float>
          }
        }
'''
class AudioCache(object):

    def __init__(self):
        self.scripts = PraatScripts()

    # TODO:
    # First chunks wav into separate files, one
    # for each word in timestamps, and then stores them into the DB.
    # @cherrypy.expose
    def chunknstore(self, user, wav, timestamps):
        # .. tbi ..
        return None

    # Stores a wav representing a single word into the DB.
    # > Returns 1 if successful, -1 if failed.
    @cherrypy.expose
    def store(self, user, word, wav):

        # If user exists...
        if user_collection.find_one({'user':user}) is not None:

            # Store wav on file system:
            # TODO: Change this to different folder
            (_, wavfile) = storeTempWAV(wav)

            # == Get various properties ==
            # Extract pitch contour + normalize
            (X, Y) = self.scripts.extractPitchContour(wavfile)
            (X, Y) = eliminateNullPoints(X, Y)
            (avgpitch, stdeviation) = computeMeanAndDeviation(Y)
            dur = X[-1]
            nY = normalizeToUnitSquare(X, Y) # we don't need X anymore b/c dx is constant

            # Process wav and insert into db:
            wrd = { 'user': user,
                    'word': word,
                    'audio': wavfile,
                    'properties': {
                        'pitch': {
                            'contour':nY,
                            'avg':avgpitch,
                            'deviation':stdeviation
                        },
                        'duration':dur
                    }
            }

            print('Remembered that user ' + str(user) + ' said ' + str(word) + '.')
            words_collection.insert_one(wrd)

            return 1

        else:
            print('Could not find user ' + str(user) + '.')
            return -1

    # Try to get the closest 'matching' audio for the given word, if possible.
    # NOTE: Right now this just returns the first word it finds. Later on we should
    # pass *ideal* properties we'd like to see in the response, like matching a rough pitch contour.
    @cherrypy.expose
    def get(self, user, word, examplewav):
        if examplewav is not None:
            # TODO: do some property matching here...
            print('This feature tbi.')

        if user_collection.find_one({'user':user}) is not None:

            wrd = words_collection.find_one({'user':user, 'word':word })
            if wrd is None:
                print('User has never said "' + str(word) + '".')
                return 0

            # Check that audio file exists...
            if not os.path.exists(wrd['audio']):
                print('User said "' + str(word) + '" before, but we couldn\'t find the audio file. :(')
                return -2

            # Match found! This user has said this word before.
            # Now we should really prosody synthesize the word,
            # but I'm going to leave that as a TODO. ^_^
            return serve_file(wrd['audio'], content_type='audio/wav', disposition='attachment')

        else:
            print('Could not find user ' + str(user) + '.')
            return -1


def storeTempWAV(wavfile):
    (fd, filename) = tempfile.mkstemp('.wav')
    with open(filename, 'wb') as f:
        f.write(wavfile.file.read())
    os.chmod(filename, 0o755)
    return (fd, filename)
def storeTempTXT(txt):
    (fd, filename) = tempfile.mkstemp('.txt')
    with open(filename, 'wb') as f:
        f.write(txt)
    os.chmod(filename, 0o755)
    return (fd, filename)
def storeTempGrid(txtgrid):
    (fd, filename) = tempfile.mkstemp()
    tgt.io.write_to_file(txtgrid, filename, format='short', encoding='utf8')
    os.chmod(filename, 0o755)
    return filename
def storeTempPitchTier(dataX, dataY): # this is the short version, which is what praatUtil can read
    (fd, filename) = tempfile.mkstemp()
    with open(filename, 'wb') as f:
        f.write('File type = "ooTextFile"\nObject class = "PitchTier"\n\n')
        f.write(str(dataX[0]) + '\n')
        f.write(str(dataX[-1]) + '\n')
        f.write(str(len(dataX)-2) + '\n')
        for i in xrange(1, len(dataX)-1):
            f.write(str(dataX[i]) + '\n')
            f.write(str(dataY[i]) + '\n')
    os.chmod(filename, 0o755)
    return filename
def storeTempDurTier(wavdur, durps): # this is the short version, which is what praatUtil can read
    (_, filename) = tempfile.mkstemp()
    with open(filename, 'wb') as f:
        f.write('File type = "ooTextFile"\nObject class = "DurationTier"\n\n')
        f.write('0\n')
        f.write(str(wavdur) + '\n')
        f.write(str(len(durps) / 2) + '\n')
        for i in xrange(len(durps)):
            f.write(str(durps[i]) + '\n')
    # with open(filename, 'r') as f:
    #     print(f.read())
    os.chmod(filename, 0o755)
    return filename
def storeTempIntensityTier(dataX, dataY):
    (_, filename) = tempfile.mkstemp()
    with open(filename, 'wb') as f:
        f.write('File type = "ooTextFile"\nObject class = "IntensityTier"\n\n')
        f.write(str(dataX[0]) + '\n')
        f.write(str(dataX[-1]) + '\n')
        f.write(str(len(dataX)-2) + '\n')
        for i in xrange(0, len(dataX)):
            f.write(str(dataX[i]) + '\n')
            f.write(str(dataY[i]) + '\n')
    with open(filename, 'r') as f:
         print(f.read())
    os.chmod(filename, 0o755)
    return filename
def stringToTimestamps(strg):
    s = strg.split(',')
    ts = []
    for i in xrange(0, len(s), 3):
        ts.append([s[i], float(s[i+1]), float(s[i+2])])
    return ts

### Removes any zeros in data
# * In practice we want to do this b/c the timestamps may have invalid 'holes' where bgn=end=0
# * to represent areas in the transcript that we don't have audio for.
def withoutZeros(Y):
    return [y for y in Y if y > 0.0001]

### Given list of data points, returns standard deviation.
def computeMeanAndDeviation(Y):
    if type(Y[0]) is tuple:
        Y = [Y[i][1] for i in xrange(len(Y))] # unzip the y-component of a graph
    u = sum(Y) / len(Y) # mean
    return (u, math.sqrt(sum([(y - u)*(y - u) for y in Y]) / len(Y)))
def computeMean(Y):
    if type(Y[0]) is tuple:
        Y = [Y[i][1] for i in xrange(len(Y))]
    return sum(Y) / len(Y)


'''
    Exposes the Praat API to a local web server.
'''

class PraatScripts(object):
    @cherrypy.expose
    def index(self):
        obj = {'filename':'sample.wav'}
        return self.avgpitch(wavfile=obj);
        #return "Hello World!" # help page should appear here

    # For setup testing.
    @cherrypy.expose
    def echo(self, txt):
        return txt

    # For debugging.
    @cherrypy.expose
    def debug(self):
        # Send back the resynth'd WAV file
        f = open('/private/var/folders/32/zxd7h2697p71r5nr7yr471wc0000gn/T/tmpQIeMmc', 'r')
        return f
        # return serve_file('/private/var/folders/32/zxd7h2697p71r5nr7yr471wc0000gn/T/tmpQIeMmc', content_type='audio/wav', disposition='attachment')

    # Performs forced alignment w/ HTK.
    # Returns an array of timestamp objects { word, t_bgn, t_end } (in order).
    @cherrypy.expose
    def align(self, wavfile=None, transcript=None):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if wavfile == None or transcript == None:
            return 'Error: Forced alignment needs a transcript.'

        # Store temp WAV to disk
        (fd, wavname) = storeTempWAV(wavfile)

        # Store temp transcript to disk
        (td, trsname) = storeTempTXT(transcript)

        # Run Penn Phonetics Lab Forced Alignment Toolkit (P2FA)
        (bd, alignfile) = tempfile.mkstemp()

        # return 'Checking: ' + wavname + ' ' + trsname + ' ' + alignfile

        cmd = ['python', 'p2fa/align.py', wavname, trsname, alignfile]
        # cmd = ['mediainfo', wavname] # debug -- check whether it's really a wav file...
        p = subprocess.call(cmd) # Call HTK and wait for HTK to finish.

        # Read output. Convert TextGrid to timestamp array.
        def textgrid_to_timestamps(txtgrid):
            ts = ""
            try:
                tg = tgt.io.read_textgrid(txtgrid)
                if tg.has_tier('word'):
                    wrdtier = tg.get_tier_by_name('word')
                    annots = wrdtier.annotations
                    for a in annots:
                        if a.text == 'sp': continue # skip spaces
                        ts += " ".join([ str(a.text), str(a.start_time), str(a.end_time) ]) + " "
                else:
                    return 'Error: No word tier.'
            except Exception, err:
                return 'Error: Could not open TextGrid ' + txtgrid + '. ' + str(err)
            return ts

        timestamps = textgrid_to_timestamps(alignfile)

        print('Timestamps: ' + timestamps);
        print('(Timestamps are stored @ ' + alignfile + ')');

        os.remove(wavname)
        os.remove(trsname)
        os.remove(alignfile)

        # Return timestamp array.
        return timestamps

    # General 'synthesize' function.
    @cherrypy.expose
    def synthesize(self, srcwav=None, srctimestamps=None, twav=None, ttimestamps=None, options="prosody,duration"):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if isinstance(srcwav, cherrypy._cpreqbody.Entity) and srcwav.file == None:
            return 'Error: Synthesis needs source wav.'
        if isinstance(twav, cherrypy._cpreqbody.Entity) and twav.file == None:
            return 'Error: Synthesis needs target wav.'
        if isinstance(srctimestamps, cherrypy._cpreqbody.Entity):
            srctimestamps = srctimestamps.fullvalue()
        if isinstance(ttimestamps, cherrypy._cpreqbody.Entity):
            ttimestamps = ttimestamps.fullvalue()
        if isinstance(options, cherrypy._cpreqbody.Entity):
            options = options.fullvalue()

        if srcwav == None or twav == None:
            return 'Error: Synthesis needs both source (srcwav) and target (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Synthesis needs both source and target timestamps.'

        prosody = 'prosody' in options
        intensity = 'intensity' in options
        duration = 'duration' in options

        print('Source timestamps (raw): ' + str(srctimestamps))
        print('Target timestamp (raw): ' + str(ttimestamps))
        srctimestamps = stringToTimestamps(srctimestamps)
        ttimestamps = stringToTimestamps(ttimestamps)
        print('Source timestamps: ' + str(srctimestamps))
        print('Target timestamps: ' + str(ttimestamps))

        # Store source and target WAVs to disk
        (_, srcname) = storeTempWAV(srcwav)
        (_, tname)   = storeTempWAV(twav)

        # CONVERT TTS AUDIO TO WAV.
        # * IN the future, we shouldn't have to do this. But Watson returns
        # * a WAV file that Praat can't read. So we need to convert the audio after-the-fact. (sigh)
        nname = tname[:-4] + '_.wav'
        convertAudioToWAV(tname, nname)
        os.remove(tname)
        tname = nname

        # Synthesis operations
        synthpath = tname

        # ! ORDER OF OPERATIONS IS IMPORTANT !
        # Perform prosodic transfer first (these calls are blocking):
        if prosody:
            synthpath = self.praat_prosody(srcname, srctimestamps, synthpath, ttimestamps, 20)

        # Intensity next
        if intensity:
            synthpath = self.praat_intensity(srcname, srctimestamps, synthpath, ttimestamps)

        # Duration last. Note that duration invalidates timestamp info.
        if duration:
            synthpath = self.praat_duration(srctimestamps, synthpath, ttimestamps)
            ttimestamps = srctimestamps

        # Teardown
        os.remove(srcname)

        # Serve file back to client
        return serve_file(synthpath, content_type='audio/wav', disposition='attachment')

    @cherrypy.expose
    def intensitysynthesis(self, srcwav=None, srctimestamps=None, twav=None, ttimestamps=None):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if srcwav == None or twav == None:
            return 'Error: Synthesis needs both source (srcwav) and target (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Synthesis needs both source and target timestamps.'

        srctimestamps = stringToTimestamps(srctimestamps)
        ttimestamps = stringToTimestamps(ttimestamps)
        print('Source timestamps: ' + str(srctimestamps))
        print('Target timestamps: ' + str(ttimestamps))

        # Store source and target WAVs to disk
        (_, srcname) = storeTempWAV(srcwav)
        (_, tname)   = storeTempWAV(twav)

        # CONVERT TTS AUDIO TO WAV.
        # * IN the future, we shouldn't have to do this. But Watson returns
        # * a WAV file that Praat can't read. So we need to convert the audio after-the-fact. (sigh)
        nname = tname[:-4] + '_.wav'
        convertAudioToWAV(tname, nname)
        os.remove(tname)
        tname = nname

        resynthpath = praat_intensity(srcname, srctimestamps, tname, ttimestamps)

        os.remove(srcname)

        # Send back the resynth'd WAV file
        return serve_file(resynthpath, content_type='audio/wav', disposition='attachment')

    # Matches duration of src words to target words in audio file.
    @cherrypy.expose
    def durationsynthesis(self, srctimestamps=None, twav=None, ttimestamps=None):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if twav == None:
            return 'Error: Duration synthesis needs target audio (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Duration synthesis needs both source and target timestamps.'

        srctimestamps = stringToTimestamps(srctimestamps)
        ttimestamps = stringToTimestamps(ttimestamps)
        print('Source timestamps: ' + str(srctimestamps))
        print('Target timestamps: ' + str(ttimestamps))

        # Store target WAV to disk
        (_, tname)   = storeTempWAV(twav)

        # CONVERT TTS AUDIO TO WAV.
        # * IN the future, we shouldn't have to do this. But Watson returns
        # * a WAV file that Praat can't read. So we need to convert the audio after-the-fact. (sigh)
        nname = tname[:-4] + '_.wav'
        convertAudioToWAV(tname, nname)
        os.remove(tname)
        tname = nname

        resynthpath = praat_duration(srctimestamps, tname, ttimestamps)

        # Send back the resynth'd WAV file
        return serve_file(resynthpath, content_type='audio/wav', disposition='attachment')

    # Transfers prosody from original WAV to TTS WAV through Praat.
    # Takes: The two WAV files and their corresponding timestamp data as a paired sequence.
    # Returns: The resynthesized TTS WAV.
    @cherrypy.expose
    def prosodicsynthesis(self, srcwav=None, srctimestamps=None, twav=None, ttimestamps=None):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if srcwav == None or twav == None:
            return 'Error: Synthesis needs both source (srcwav) and target (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Synthesis needs both source and target timestamps.'

        srctimestamps = stringToTimestamps(srctimestamps)
        ttimestamps = stringToTimestamps(ttimestamps)
        print('Source timestamps: ' + str(srctimestamps))
        print('Target timestamps: ' + str(ttimestamps))

        # Store source and target WAVs to disk
        (_, srcname) = storeTempWAV(srcwav)
        (_, tname)   = storeTempWAV(twav)

        # CONVERT TTS AUDIO TO WAV.
        # * IN the future, we shouldn't have to do this. But Watson returns
        # * a WAV file that Praat can't read. So we need to convert the audio after-the-fact. (sigh)
        nname = tname[:-4] + '_.wav'
        convertAudioToWAV(tname, nname)
        os.remove(tname)
        tname = nname

        # Perform prosody transfer on stored files via Praat scripts
        resynthpath = praat_prosody(srcname, srctimestamps, tname, ttimestamps)

        os.remove(srcname)

        # Send back the resynth'd WAV file
        return serve_file(resynthpath, content_type='audio/wav', disposition='attachment')

    # PRIVATE: PRAAT TRANSFER METHODS
    def praat_prosody(self, srcname, srctimestamps, tname, ttimestamps, transferThreshold=0):

        # Extract pitch contour from source WAV
        (_, pitchtierpath) = tempfile.mkstemp()
        print('Reading pitch tier from src WAV ' + srcname + ' to filepath ' + pitchtierpath)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_pitchtier.praat', srcname, pitchtierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pitchtierpath_resp = p.stdout.readline()
        if not pitchtierpath_resp:
            return 'Error: Could not read pitch tier filename from stdout.'

        # EXPERIMENTAL: Extract pitch contour from TTS WAV
        (_, tpitchtierpath) = tempfile.mkstemp()
        print('Reading pitch tier from TTS WAV ' + tname + ' to filepath ' + tpitchtierpath)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_pitchtier.praat', tname, tpitchtierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tpitchtierpath_resp = p.stdout.readline()
        if not tpitchtierpath_resp:
            return 'Error: Could not read tts pitch tier filename from stdout.'

        # Read src pitch tier into memory
        print('Reading from source pitch tier file: ' + pitchtierpath)
        (X, Y) = praatUtil.readPitchTier(pitchtierpath)

        print('Reading from TTS pitch tier file: ' + tpitchtierpath)
        (ttsX, ttsY) = praatUtil.readPitchTier(tpitchtierpath)

        def _getTTSPitchAroundPoint(ptX):
            minX = 10000000
            minI = 0
            for i in xrange(len(ttsX)): # Find closest point
                dist = (ttsX[i] - ptX) * (ttsX[i] - ptX)
                if dist < minX:
                    minX = dist
                    minI = i
            return ttsY[minI] # lazy but let's see how this fares

        def _getPitchPointsInSegment(bgn, end, A, B):
            pps = []
            for i in xrange(len(A)):
                x = A[i]
                y = B[i]

                # if i > 0 and A[i-1] < bgn and x >= bgn: # append intersection point w/ bgn
                #     ratio = (bgn - A[i-1]) / (x - A[i-1])
                #     pps.append([bgn, ratio * y + (1.0 - ratio) * B[i-1]])

                if x >= bgn and x < end:
                    pps.append([x, y])
                elif x >= end:
                    # if i > 0 and A[i-1] < end: # append intersection point w/ end
                    #     ratio = (end - A[i-1]) / (x - A[i-1])
                    #     pps.append([bgn, ratio * y + (1.0 - ratio) * B[i-1]])
                    break
            return pps # format [x, y]

        # Transpose pitch points from source to target, according to timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get the pitch points contained in it.
        # -> 3. Translate + scale the pitch points to the corresponding target segment.
        # -> 4. OPT: Normalize pitch Hz using target's avg pitch, and OPT scale Y using std deviation
        # -> 5. Write result (tX, tY) into new pitch tier and save
        #_, nY = normalizeToUnitSquare(X, withoutZeros(Y))
        (src_mean, src_stdeviation) = computeMeanAndDeviation(withoutZeros(Y))
        #src_mean *= max(Y) - min(Y)
        (tgt_mean, tgt_stdeviation) = computeMeanAndDeviation(withoutZeros(ttsY))
        print('srcmean --------> ' + str(src_mean))
        print('srcdev --------> ' + str(src_stdeviation))
        tX = []
        tY = []
        for i in range(len(srctimestamps)):
            srcts = srctimestamps[i]
            tgtts = ttimestamps[i]
            bgn = srcts[1]
            end = srcts[2]
            if bgn == 0 and end == 0:
                continue # Skip null timestamps.
            tbgn = tgtts[1]
            tend = tgtts[2]
            lensrc = end - bgn
            lentgt = tend - tbgn
            pps = _getPitchPointsInSegment(bgn, end, X, Y)

            if abs(tbgn - tend) < 0.00001:# or len(pps) == 0 or len(tpps) == 0:
                tpps = _getPitchPointsInSegment(tbgn, tend, ttsX, ttsY)
                for m in xrange(len(tpps)):
                    tX.append(tpps[m][0])
                    tY.append(tpps[m][1])
                print('(skipping "' + srcts[0] + '")')
                continue # Skip the prosody transfer for null words

            if transferThreshold != 0:
                tpps = _getPitchPointsInSegment(tbgn, tend, ttsX, ttsY)

                # print('Calculating difference between prosodic curves for "' + srcts[0] + '"...')
                if len(tpps) == 0 or len(pps) == 0:
                    rmse = 0
                    area = 0
                else:

                    rmse = math.sqrt(mean_squared_error(toTupleList(pps), toTupleList(tpps), bgn, end, tbgn, tend))
                    #print('Root mean squared error: ' + str(rmse))

                    #(tpps_mean, _) = computeMeanAndDeviation(normalizeDx(tpps))
                    #(pps_mean, _) = computeMeanAndDeviation(normalizeDx(pps))
                    #norm_tpps = mapSubtractY(mapToInterval(toTupleList(tpps), (tbgn, tend), (0, 100)), tpps_mean - 1000)
                    #norm_pps = mapSubtractY(mapToInterval(toTupleList(pps), (bgn, end), (0, 100)), pps_mean - 1000) # that -1000 ensures all the y's will be > 0 for areaBetween.
                    #area = areaBetween(norm_pps, norm_tpps)

                # print('Difference between prosodic curves for "' + srcts[0] + '" is ', area)
                if rmse < transferThreshold:
                    for m in xrange(len(tpps)):
                        tX.append(tpps[m][0])
                        tY.append(tpps[m][1])
                    print('(skipping "' + srcts[0] + '" with rms ' + str(rmse) + ')')
                    continue # Skip the prosody transfer for this word b/c it doesn't clear our threshold difference.

            print('Transferring prosody for word "' + srcts[0] + '" with rms ' + str(rmse))
            for p in pps:
                if p[1] > src_mean * 2.5: continue # skip outliers

                dx = p[0] - bgn # x = px - dx ... x2 + tdx = tx ... x2 = ttimestamps[i]['t_bgn'] ... tdx = (dx / (end-bgn)) * (tend-tbgn)
                tdx = (dx / lensrc) * lentgt
                tp = tbgn + tdx # timestamp transform... ???

                # Find nearest value in TTS wav's pitch contour...
                #tts_pitch = _getTTSPitchAroundPoint(tp)

                # Pitch renormalization
                # RESCALE SRC Y BY ST DEVIATION --> rescaled_src_pitch = (src_pitch - src_avgpitch) / src_stdeviation * t_stdeviation
                # TRANSLATE SRC Y TO NEW MEAN --> rescaled_src_pitch + (t_avgpitch - src_avgpitch)

                # renormalize w/ mean + st deviation
                tv = ((p[1] - src_mean) / src_stdeviation * tgt_stdeviation) + tgt_mean

                # renormalize w/ just mean offset
                #tv = p[1] / src_mean * tgt_mean

                # one-to-one mapping
                #tv = p[1]

                tX.append(tp)
                tY.append(tv)
        tpitchtier = storeTempPitchTier(tX, tY) # will need to figure out xmin and xmax properties ...

        # Run Praat resynthesis script.
        (_, resynthpath) = tempfile.mkstemp()
        print('Resynthing to tmpfile: ' + resynthpath + ' using tts audio: ' + tname)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/pitch_resynth.praat', tname, tpitchtier, resynthpath] # --> need to write script
        print('Running Praat with command: ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.wait()

        '''
        # Convert timestamps to Interval TextGrids and store
        srcgrid = timestamps_to_textgrid(srctimestamps) # --> need to implement
        trggrid = timestamps_to_textgrid(ttimestamps) #   --> need to implement
        srcgrid = storeTempGrid(srcgrid)
        trggrid = storeTempGrid(trggrid)

        # Run Praat resynthesis script.
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/prosody_transfer.praat', srcname, srcgrid, tname, trggrid] # --> need to write script
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)'''

        # Error checking...
        # Read the filename of the resynthesized file.
        resynthpath_resp = p.stdout.readline()
        if not resynthpath_resp:
            return 'Error: Could not read filename from stdout.'

        print('Praat response: ' + resynthpath_resp)

        # Teardown
        os.remove(pitchtierpath)
        os.remove(tpitchtierpath)
        os.remove(tpitchtier)
        os.remove(tname)

        return resynthpath;

    def praat_intensity(self, srcname, srctimestamps, tname, ttimestamps):

        # Extract intensity contour from source WAV
        (_, inttierpath) = tempfile.mkstemp()
        print('Reading intensity tier from src WAV ' + srcname + ' to filepath ' + inttierpath)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_intensitytier.praat', srcname, inttierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.wait()
        resp = p.stdout.readline()
        if not resp:
            return 'Error: Could not read intensity tier filename from stdout.'

        # Extract intensity contour from target WAV
        (_, inttierpath_tgt) = tempfile.mkstemp()
        print('Reading intensity tier from target WAV ' + tname + ' to filepath ' + inttierpath_tgt)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_intensitytier.praat', tname, inttierpath_tgt]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.wait()
        resp = p.stdout.readline()
        if not resp:
            return 'Error: Could not read intensity tier filename from stdout.'

        # Read intensity tiers into memory
        print('Reading from source intensity tier file: ' + inttierpath)
        (X, Y) = praatUtil.readIntensityTier(inttierpath)
        print('Reading from target intensity tier file: ' + inttierpath_tgt)
        (tX, tY) = praatUtil.readIntensityTier(inttierpath_tgt)

        # Calculate avg intensity for each word
        # Calculate avg intensity for the whole sentence
        (avgint_src, stdeviation_src) = computeMeanAndDeviation(withoutZeros(Y)) # TODO: Weight points by area...
        (avgint_tgt, stdeviation_tgt) = computeMeanAndDeviation(withoutZeros(tY)) # TODO: Weight points by area...

        tintmax = max(tY)
        #aY = []
        #for i in xrange(len(Y)):
        #    aY.append(tintmax - Y[i])

        def _getIntPointsInSegment(bgn, end, X, Y):
            pps = []
            for i in xrange(len(X)):
                x = X[i]
                y = Y[i]
                if x >= bgn and x < end:
                    pps.append([x, y])
            return pps # format [x, y]
        def _getAvgInt(pps):
            avg = 0
            for i in xrange(len(pps)):
                avg += pps[i][1]
            return avg / len(pps)

        # Transpose intensity points from source to target, according to timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get the intensity points contained in it.
        # -> 3. Translate + scale the intensity points to the corresponding target segment.
        # -> 4. // OPT: Normalize intensity target's avg intensity, and OPT scale Y using std deviation
        # -> 5. Write result (tX, tY) into new intensity tier and save
        aX = []
        aY = []
        for i in range(len(srctimestamps)):
            srcts = srctimestamps[i]
            tgtts = ttimestamps[i]
            bgn = srcts[1]
            end = srcts[2]
            if bgn == 0 and end == 0:
                continue # Skip null timestamps.
            tbgn = tgtts[1]
            tend = tgtts[2]

            # Get part of the intensity contour corresponding to this ts interval
            pps = _getIntPointsInSegment(bgn, end, X, Y)
            tpps = _getIntPointsInSegment(tbgn, tend, tX, tY)

            if len(pps) == 0 or len(tpps) == 0:
                print('Warning @ praat_intensity: skipping word-intensity gap. TODO: fix in future!')
                continue



            # DEBUG: Invert contour
            '''for k in xrange(len(tpps)):
                tp = tpps[k]
                tx = tp[0]
                ty = tintmax - tp[1]
                aX.append(tx)
                aY.append(ty)
            continue'''

            for p in pps:
                dx = p[0] - bgn
                tdx = (dx / (end-bgn)) * (tend-tbgn)
                tp = tbgn + tdx
                aX.append(tp)
                aY.append(p[1] / avgint_src * avgint_tgt)
            continue

            # Calculate average intensity of the word
            avgint_word = max(_getAvgInt(pps), 0)
            avgint_word_tgt = max(_getAvgInt(tpps), 0)

            if avgint_word_tgt == 0 or avgint_word == 0:
                avgint_word = avgint_src
                avgint_word_tgt = avgint_tgt

            # Compute how the word's intensity differs from the avg
            intmult_src = avgint_word / avgint_src # e.g., 120% intensity = 1.2
            intmult_tgt = avgint_word_tgt / avgint_tgt

            # Transfer intensity by scaling src to target
            # NOTE: This is interval will get _multiplied_ with the target audio. So if
            # we want no change, all intervals will equal 1. Consider if the src intensity is 20% greater
            # than avg, and the target intensity is 20% less. Now intmult_src=1.2 and intmult_tgt=0.8.
            # intmult_src / intmult_tgt would equal 1.5, corresponding to a 50% increase. Conversely,
            # scaling target 1.2 to src 0.8 corresponds to a 33.3% decrease. Does that make sense?
            aX.append(tbgn+0.000001)
            aY.append(avgint_tgt * (intmult_src / intmult_tgt)) # if intensity variations are equal, this will do nothing!
            aX.append(tend-0.000001)
            aY.append(avgint_tgt * (intmult_src / intmult_tgt))

        tinttier = storeTempIntensityTier(aX, aY) # will need to figure out xmin and xmax properties ...

        # Run Praat resynthesis script.
        (_, resynthpath) = tempfile.mkstemp()
        print('Resynthing to tmpfile: ' + resynthpath + ' using tts audio: ' + tname)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/intensity_resynth.praat', tname, tinttier, resynthpath] # --> need to write script
        print('Running Praat with command: ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.wait()

        # Error checking...
        # Read the filename of the resynthesized file.
        resp = p.stdout.readline()
        if not resp:
            return 'Error: Could not read filename from stdout.'

        print('Praat response: ' + resp)

        # Teardown
        os.remove(inttierpath)
        os.remove(inttierpath_tgt)
        os.remove(tinttier)
        os.remove(tname)

        return resynthpath

    def praat_duration(self, srctimestamps, tname, ttimestamps):
        # Build duration tier from timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get its duration.
        # -> 3. Add duration points to mark the start and end of each word.
        # -> 4. Save duration tier to disk.
        durps = []
        wavdur = ttimestamps[-1][2]
        prev_tbgn = 0
        prev_tend = 0
        prev_bgn = 0
        prev_end = 0
        for i in range(len(srctimestamps)):
            srcts = srctimestamps[i]
            tgtts = ttimestamps[i]
            bgn = srcts[1]
            end = srcts[2]
            if bgn == 0 and end == 0:
                continue # Skip null timestamps.
            tbgn = tgtts[1]
            tend = tgtts[2]
            durspace = prev_end - bgn
            tdurspace = prev_tend - tbgn
            dursrc = end - bgn
            durtgt = tend - tbgn

            if dursrc > durtgt:
                ratio = 1.0 # don't stretch.
            else:
                ratio = dursrc / (durtgt + 0.00001)
                if ratio < 0.5: ratio = 0.5 # don't shrink too much
            bgn_space_ratio = 1.0

            if durspace > 0 and tdurspace > 0: # We should scale the spaces too!
                bgn_space_ratio = durspace / tdurspace
                durps[-1] = bgn_space_ratio # we make sure the previous point mirrors the new duration for the space.
            #elif len(durps) > 0:
            #    durps = durps[:-2]

            durps.extend([tbgn, bgn_space_ratio, tbgn+0.00001, ratio, tend-0.00001, ratio, tend, 1.0])

            prev_bgn = bgn
            prev_end = end
            prev_tbgn = tbgn
            prev_tend = tend
        tdurtier = storeTempDurTier(wavdur, durps) # Store DurationTier data to disk.

        # Run Praat resynthesis script.
        (_, resynthpath) = tempfile.mkstemp()
        print('Resynthing to tmpfile: ' + resynthpath + ' using tts audio: ' + tname)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/dur_resynth.praat', tname, tdurtier, resynthpath] # --> need to write script
        print('Running Praat with command: ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.wait()

        # Error checking...
        # Read the filename of the resynthesized file.
        resynthpath_resp = p.stdout.readline()
        if not resynthpath_resp:
            return 'Error: Could not read filename from stdout.'

        print('Praat response: ' + resynthpath_resp)

        # Teardown
        os.remove(tdurtier)
        os.remove(tname)

        return resynthpath

    # Extract pitch contour from WAV
    def extractPitchContour(self, wavfile):
        (_, pitchtierpath) = tempfile.mkstemp()
        print('Extracting pitch tier from WAV file ' + srcname + ' to filepath ' + pitchtierpath)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_pitchtier.praat', wavfile, pitchtierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pitchtierpath_resp = p.stdout.readline()
        if not pitchtierpath_resp:
            return 'Error: Could not read pitch tier filename from stdout.'

        # Read src pitch tier into memory
        print('Reading from pitch tier file: ' + pitchtierpath)
        return praatUtil.readPitchTier(pitchtierpath)

    # Listens for a POST'd WAV file and returns its average pitch,
    # calculated by a Praat subprocess.
    @cherrypy.expose
    def avgpitch(self, wavfile=None, fname=None):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if wavfile == None:
            return 'Error: Try POSTing a wav file.'

        # Store WAV to disk in temp file:
        (fd, filename) = storeTempWAV(wavfile)

        # According to https://cherrypy.readthedocs.org/en/3.2.6/progguide/files/uploading.html,
        # files posted with enctype="multipart/form-data" are automatically saved
        # to a temp file in the local directory. The object 'wavfile'
        # exposes the .filename of the stored file, and the .content_type (MIME).
        # For us, this is convenient because Praat's CLI can only read data from the disk.

        # Run Praat to analyze avg pitch.
        #return wavfile['filename']
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/avg_pitch.praat', filename, '10', '75', '500', '11025']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Teardown
        os.remove(filename)

        # Read result
        while True:
            line = p.stdout.readline()
            if not line:
                return 'Error: unknown.'
                break
            return line

''' Cross-origin reference stuff, to get around Chrome's restrictions on communicating w/ same-host servers. '''
def CORS():
    cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

config = {'/': { 'tools.CORS.on': True}}
cherrypy.tools.CORS = cherrypy.Tool('before_finalize', CORS)

## HTTPS + SSL
cherrypy.server.ssl_module = 'builtin'
cherrypy.server.ssl_certificate = "ssl/cert.pem"
cherrypy.server.ssl_private_key = "ssl/privkey.pem"

#cherrypy.quickstart(PraatScripts(), config=config)
cherrypy.tree.mount(PraatScripts(), "/", config=config)
cherrypy.tree.mount(AudioCache(), "/db", config=config)
cherrypy.engine.start()
cherrypy.engine.block()

#ps = PraatScripts()
#ps.debug()

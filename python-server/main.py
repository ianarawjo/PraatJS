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

# Database (you should be running mongod)
from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client['newspeak']
words_collection = db['words'] # DB is called 'newspeak' and Collection is called 'words'
user_collection = db['users'] # for safety reasons

constants = { 'SEGMENTS':40 }

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
            y = a * Y[j] + (1.0 - a) * Y[j-1]

        nY.append(y)

    return nY

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
    return (fd, filename)
def storeTempTXT(txt):
    (fd, filename) = tempfile.mkstemp('.txt')
    with open(filename, 'wb') as f:
        f.write(txt)
    return (fd, filename)
def storeTempGrid(txtgrid):
    (fd, filename) = tempfile.mkstemp()
    tgt.io.write_to_file(txtgrid, filename, format='short', encoding='utf8')
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
    return filename
def storeTempDurTier(wavdur, durps): # this is the short version, which is what praatUtil can read
    (_, filename) = tempfile.mkstemp()
    with open(filename, 'wb') as f:
        f.write('File type = "ooTextFile"\nObject class = "DurationTier"\n\n')
        f.write('0')
        f.write(str(wavdur) + '\n')
        f.write(str(len(durps) / 2) + '\n')
        for i in xrange(len(durps)):
            f.write(str(durps[i]) + '\n')
    return filename
def storeTempIntensityTier(dataX, dataY):
    (_, filename) = tempfile.mkstemp()
    with open(filename, 'wb') as f:
        f.write('File type = "ooTextFile"\nObject class = "IntensityTier"\n\n')
        f.write(str(dataX[0]) + '\n')
        f.write(str(dataX[-1]) + '\n')
        f.write(str(len(dataX)-2) + '\n')
        for i in xrange(1, len(dataX)-1):
            f.write(str(dataX[i]) + '\n')
            f.write(str(dataY[i]) + '\n')
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
    u = sum(Y) / len(Y) # mean
    return (u, math.sqrt(sum([(y - u)*(y - u) for y in Y]) / len(Y)))


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

        # Return timestamp array.
        return timestamps

    # General 'synthesize' function.
    @cherrypy.expose
    def synthesize(self, srcwav=None, srctimestamps=None, twav=None, ttimestamps=None, options="prosody,duration"):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        if srcwav == None or twav == None:
            return 'Error: Synthesis needs both source (srcwav) and target (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Synthesis needs both source and target timestamps.'

        prosody = 'prosody' in options
        intensity = 'intensity' in options
        duration = 'duration' in options

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
        tname = nname

        # Synthesis operations
        synthpath = tname

        # ! ORDER OF OPERATIONS IS IMPORTANT !
        # Perform prosodic transfer first (these calls are blocking):
        if prosody:
            synthpath = praat_prosody(srcname, srctimestamps, synthpath, ttimestamps)

        # Intensity next
        if intensity:
            synthpath = praat_intensity(srcname, srctimestamps, synthpath, ttimestamps)

        # Duration last. Note that duration invalidates timestamp info.
        if duration:
            synthpath = praat_intensity(srcname, srctimestamps, synthpath, ttimestamps)
            ttimestamps = srctimestamps

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
        tname = nname

        resynthpath = praat_intensity(srcname, srctimestamps, tname, ttimestamps)

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
        tname = nname

        # Perform prosody transfer on stored files via Praat scripts
        resynthpath = praat_prosody(srcname, srctimestamps, tname, ttimestamps)

        # Send back the resynth'd WAV file
        return serve_file(resynthpath, content_type='audio/wav', disposition='attachment')

    # PRIVATE: PRAAT TRANSFER METHODS
    def praat_prosody(self, srcname, srctimestamps, tname, ttimestamps):

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

        def _getPitchPointsInSegment(bgn, end):
            pps = []
            for i in xrange(len(X)):
                x = X[i]
                y = Y[i]
                if x >= bgn and x < end:
                    pps.append([x, y])
            return pps # format [x, y]

        # Transpose pitch points from source to target, according to timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get the pitch points contained in it.
        # -> 3. Translate + scale the pitch points to the corresponding target segment.
        # -> 4. OPT: Normalize pitch Hz using target's avg pitch, and OPT scale Y using std deviation
        # -> 5. Write result (tX, tY) into new pitch tier and save
        (src_mean, src_stdeviation) = computeMeanAndDeviation(withoutZeros(Y))
        (tgt_mean, tgt_stdeviation) = computeMeanAndDeviation(withoutZeros(ttsY))
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
            pps = _getPitchPointsInSegment(bgn, end)
            for p in pps:
                dx = p[0] - bgn # x = px - dx ... x2 + tdx = tx ... x2 = ttimestamps[i]['t_bgn'] ... tdx = (dx / (end-bgn)) * (tend-tbgn)
                tdx = (dx / lensrc) * lentgt
                tp = tbgn + tdx # timestamp transform... ???

                # Find nearest value in TTS wav's pitch contour...
                #tts_pitch = _getTTSPitchAroundPoint(tp)

                # Pitch renormalization
                # RESCALE SRC Y BY ST DEVIATION --> rescaled_src_pitch = (src_pitch - src_avgpitch) / src_stdeviation * t_stdeviation
                # TRANSLATE SRC Y TO NEW MEAN --> rescaled_src_pitch + (t_avgpitch - src_avgpitch)
                tv = ((p[1] - src_mean) / src_stdeviation * tgt_stdeviation) + (tgt_mean - src_mean)

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

        return resynthpath;

    def praat_intensity(self, srcname, srctimestamps, tname, ttimestamps):

        # Extract intensity contour from source WAV
        (_, inttierpath) = tempfile.mkstemp()
        print('Reading intensity tier from src WAV ' + srcname + ' to filepath ' + inttierpath)
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_intensitytier.praat', srcname, inttierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        resp = p.stdout.readline()
        if not resp:
            return 'Error: Could not read intensity tier filename from stdout.'

        # Read src intensity tier into memory
        print('Reading from source intensity tier file: ' + inttierpath)
        (X, Y) = praatUtil.readIntensityTier(inttierpath)

        #print('Reading from TTS pitch tier file: ' + tpitchtierpath)
        #(ttsX, ttsY) = praatUtil.readPitchTier(tpitchtierpath)

        def _getIntPointsInSegment(bgn, end):
            pps = []
            for i in xrange(len(X)):
                x = X[i]
                y = Y[i]
                if x >= bgn and x < end:
                    pps.append([x, y])
            return pps # format [x, y]

        # Transpose intensity points from source to target, according to timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get the intensity points contained in it.
        # -> 3. Translate + scale the intensity points to the corresponding target segment.
        # -> 4. // OPT: Normalize intensity target's avg intensity, and OPT scale Y using std deviation
        # -> 5. Write result (tX, tY) into new intensity tier and save
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
            pps = _getIntPointsInSegment(bgn, end)
            for p in pps:
                dx = p[0] - bgn # x = px - dx ... x2 + tdx = tx ... x2 = ttimestamps[i]['t_bgn'] ... tdx = (dx / (end-bgn)) * (tend-tbgn)
                tdx = (dx / lensrc) * lentgt
                tp = tbgn + tdx # timestamp transform... ???
                tv = p[1] # p[1] # tbi: value transform...
                tX.append(tp)
                tY.append(tv)
        tinttier = storeTempIntensityTier(tX, tY) # will need to figure out xmin and xmax properties ...

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
            ratio = dursrc / (durtgt + 0.00001)
            bgn_space_ratio = 1.0

            if durspace > 0 and tdurspace > 0: # We should scale the spaces too!
                bgn_space_ratio = durspace / tdurspace
                durps[-1] = bgn_space_ratio # we make sure the previous point mirrors the new duration for the space.

            durps.append([tbgn, bgn_space_ratio, tbgn+0.00001, ratio, tend-0.00001, ratio, tend, 1.0])

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

        return resynthpath

    def convertAudioToWAV(self, wavfile, new_filename):
        cmd = ['ffmpeg', '-i', wavfile, new_filename]
        subprocess.call(cmd)

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

config = {'/': { 'tools.CORS.on': True }}
cherrypy.tools.CORS = cherrypy.Tool('before_finalize', CORS)

#cherrypy.quickstart(PraatScripts(), config=config)
cherrypy.tree.mount(PraatScripts(), "/", config=config)
cherrypy.tree.mount(AudioCache(), "/db", config=config)
cherrypy.engine.start()
cherrypy.engine.block()

#ps = PraatScripts()
#ps.debug()

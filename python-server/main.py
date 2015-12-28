import cherrypy # Server
import tgt # TextGrid API

import subprocess
import tempfile
import os

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
        f.write('File type = "ooTextFile"\nObject class = "PitchTier"\n\n');
        f.write(str(dataX[0]) + '\n')
        f.write(str(dataX[-1]) + '\n')
        f.write(str(len(dataX)-2) + '\n')
        for i in xrange(1, len(dataX)-2):
            #f.write('points [' + str(i) + ']:\n')
            f.write(str(dataX[i]) + '\n')
            f.write(str(dataY[i]) + '\n')
    return filename


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
        return txt;

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
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Read output. Convert TextGrid to timestamp array.
        def textgrid_to_timestamps(txtgrid):
            ts = []
            try:
                tg = tgt.io.read_textgrid(txtgrid)
                if tg.has_tier('word'):
                    wrdtier = tg.get_tier_by_name('word')
                    annots = wrdtier.annotations
                    for a in annots:
                        if a.text == 'sp': continue # skip spaces
                        ts.append([ a.text, a.start_time, a.end_time ])
                else:
                    return 'Error: No word tier.'
            except Exception, err:
                return 'Error: Could not open TextGrid ' + txtgrid + '. ' + str(err)
            return ts

        timestamps = textgrid_to_timestamps(alignfile)

        # Return timestamp array.
        return timestamps


    # Transfers prosody from original WAV to TTS WAV through Praat.
    # Takes: The two WAV files and their corresponding timestamp data as a paired sequence.
    # Returns: The resynthesized TTS WAV.
    @cherrypy.expose
    def prosodicsynthesis(self, srcwav=None, srctimestamps=None, twav=None, ttimestamps=None):
        if srcwav == None or ttswav == None:
            return 'Error: Synthesis needs both source (srcwav) and target (twav).'
        elif srctimestamps == None or ttimestamps == None:
            return 'Error: Synthesis needs both source and target timestamps.'

        # Store source and target WAVs to disk
        (_, srcname) = storeTempWAV(srcwav)
        (_, tname)   = storeTempWAV(twav)

        # Extract pitch contour from source WAV
        (_, pitchtierpath) = tempfile.mkstemp()
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/extract_pitchtier.praat', srcname, pitchtierpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pitchtierpath = p.stdout.readline()
        if not pitchtierpath:
            return 'Error: Could not read pitch tier filename from stdout.'

        # Read pitch tier into memory
        (X, Y) = praatUtil.readPitchTier(pitchtierpath)

        def _getPitchPointsInSegment(bgn, end):
            pps = []
            for x, y in X, Y:
                if x >= bgn and x < end:
                    pps.append([x, y])
            return pps # format [x, y]

        # Transpose pitch points from source to target, according to timestamp data.
        # -> 1. Loop through all source segments (words).
        # -> 2. For each segment, get the pitch points contained in it.
        # -> 3. Translate + scale the pitch points to the corresponding target segment.
        # -> 4. OPT: Normalize pitch Hz using target's avg pitch, and OPT scale Y using std deviation
        # -> 5. Write result (tX, tY) into new pitch tier and save
        tX = [], tY = []
        for i in range(len(srctimestamps)):
            srcts = srctimestamps[i]
            tgtts = ttimestamps[i]
            bgn, end = srcts['t_bgn'], srcts['t_end']
            tbgn, tend = tgtts['t_bgn'], tgtts['t_end']
            lensrc = end - bgn
            lentgt = tend - tbgn
            pps = _getPitchPointsInSegment(bgn, end)
            for p in pps:
                dx = p[0] - bgn # x = px - dx ... x2 + tdx = tx ... x2 = ttimestamps[i]['t_bgn'] ... tdx = (dx / (end-bgn)) * (tend-tbgn)
                tdx = (dx / lensrc) * lentgt
                tp = tbgn + tdx # timestamp transform... ???
                tv = p[1] # tbi: value transform...
                tX.append(tp)
                tY.append(tv)
        tpitchtier = storeTempPitchTier(tX, tY) # will need to figure out xmin and xmax properties ...

        # Run Praat resynthesis script.
        (_, resynthpath) = tempfile.mkstemp()
        cmd = ['praat/Praat.app/Contents/MacOS/Praat', '--run', 'praat/scripts/pitch_resynth.praat', tname, tpitchtier, resynthpath] # --> need to write script
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

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
        resynthpath = p.stdout.readline()
        if not resynthpath:
            return 'Error: Could not read filename from stdout.'

        # Send back the resynth'd WAV file
        return serve_file(resynthpath, 'audio/x-wav', 'attachment')


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

cherrypy.quickstart(PraatScripts(), config=config)

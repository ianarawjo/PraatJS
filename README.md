# PraatJS

** in development **

#### Server + communication module for audio analysis in JS.
PraatJS is a JS module (PraatServer) + CherryPy server (main.py) for performing audio analysis from Javascript. At a basic level, the code allows you to call [Praat](http://www.fon.hum.uva.nl/praat/) scripts from Javascript.
 * For testing, you'd host the server locally and use the module in your scripts.

##### Requirements + dependencies:
jQuery, Praat, HTK (optional). Server runs on Mac. Tested on Mac OS X 10.10.5.

#### Installation
There are three steps to getting PraatJS up and running:
1. Importing the praat.js script
2. Setting up the server and installing dependencies
2. Running the audio analysis server
##### Importing praat.js
Copy praat.js into your site directory and add to HTML:
```
<script src="praat.js"></script>
```
Make sure you have jQuery imported as well.
##### Server setup: installing dependencies
 - Download [the Praat app for Mac](http://www.fon.hum.uva.nl/praat/). Drop Praat.app into the python-server/praat directory.
 - (Optional) Install [HTK](http://htk.eng.cam.ac.uk/) if you want to use the built-in 'align' function to perform forced alignment.
##### Running the server
In Terminal, cd into the python-server directory and type:
```
python main.py
```
That's it! CherryPy takes care of the rest.
 * By default, the server runs locally on port 8080. If you want to change this, correct the HOST constants in main.py and praat.js.

## Built-in Functions
PraatJS comes with some specific scripts:
* ```calcTimestamps```: Given WAV file and transcript, performs forced alignment using HTK.
* ```calcAveragePitch```: Given WAV file, returns average 'pitch' (f0) in Hz.
* ```transferProsody```: Given a pair of speech files saying the same thing and their timestamp data, transfers the prosody (here only the pitch contour) of the source speech to the target speech.
* ```run```: See below for details.

## Running a generic script
For example, to run the script avg_pitch.praat in the python-server/praat/scripts:
```
Praat.run('avg_pitch', [wav_url, 10, 75, 500, 11025]).then(function(data) {
    doSomething(data);
});
```
where wav_url is the URL or blob url to a WAV file. **The console output from Praat will be the result of the call.** For this example, you'd get something like 135.42104541. This means that to read the results, you must modify your Praat script to output to console.
 - However, there is an exception: **If the Praat script outputs a filepath to a local file, the server will automatically load that file and send the file itself.**
 - This 'automatic conversion' also applies when passing URLs: any urls will be identified + their contents passed as data to the server.

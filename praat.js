/**
    Communicate with server running Praat + perform operations on audio.
    * Right now connects with CherryPy server running Praat. *
    * Created on Dec 26 2015 *
    @author Ian Arawjo
    @class {Praat} Praat server specification
    @version 0.0.4
    @requires jQuery
*/
var Praat = (function() {
    var pub = {};

    /**
     * The address of the server.
     * !! Change this line to match your setup. !!
     * @constant
     * @type {string}
     * @default
     */
    const HOST = 'http://localhost:8080/';

    /**
     * Advanced. Runs a praat script with arguments provided by args array.
     * !! If an argument
     * @param  {[type]} scriptname [description]
     * @param  {[type]} dataObj    [description]
     * @return {[type]}            [description]
     */
    pub.run = function(scriptname, args) {

    };

    /**
     * Performs forced alignment with HTK,
     * calculating timestamps from a speech file and a transcript.
     * NOTE: Requires HTK 3.4 (not 3.4.1) installed on the host machine. If you don't
     * need to use this function, don't mess with installing HTK 3.4 -- it's a pain.
     * @param  {string} wavurl     URL to the audio file to analyze.
     * @param  {string} transcript The transcript as one long string.
     * @return {Promise} Promise passing timestamps in the form [word, bgn, end].
     */
    pub.calcTimestamps = function(wavurl, transcript) {
        return loadBlob(wavurl).then(function(wavblob) {
            var fd = new FormData();
            fd.append('wavfile', wavblob);
            fd.append('transcript', transcript);
            return sendFormData(fd, 'align');
        });
    };

    /**
     * Calculates average pitch for WAV file at url.
     * @param  {string} wavurl URL to the audio file to analyze.
     * @return {Promise}       Promise passing the average pitch in Hz. (number)
     */
    pub.calcAveragePitch = function(wavurl) {
        return loadBlob(wavurl).then(function(wavblob) {
            var fd = new FormData();
            fd.append('wavfile', wavblob);
            return sendFormData(fd, 'avgpitch');
        });
    };

    /**
     * Given a pair of speech files saying the same thing and their timestamp data,
     * transfers the prosody (here only the pitch contour) of the source speech.
     * to the target speech.
     * @param  {string} srcurl    URL to the source audio.
     * @param  {string} targeturl URL to the target audio.
     * @param  {Array} srcts      Timestamps for the source audio.
     * @param  {Array} targetts   Timestamps for the target audio.
     * @return {Promise} Promise passing a Blob containing the resynthesized WAV file.
     */
    pub.transferProsody = function(srcurl, targeturl, srcts, targetts) {
        var _srcblob = null;
        return loadBlob(srcurl).then(function(srcblob) {
            _srcblob = srcblob;
            return loadBlob(targeturl);
        }).then(function(targetblob) {
            var fd = new FormData();
            fd.append('srcwav', _srcblob);
            fd.append('srctimestamps', srcts);
            fd.append('twav', targetblob);
            fd.append('ttimestamps', targetts);
            return sendFormData(fd, 'prosodicsynthesis');
        }).then(function(data) { // Verify data.
            return new Promise(function(resolve, reject) {
                if (typeof data === 'string') reject(data); // Error.
                else resolve(data);
            });
        });
    };

    /**
     * Loads file at URL (usually WAV) into Blob object
     * for further processing.
     * To access do loadBlob(url).then(function(blob){...});)
     * @private
     * @param  {string}   url The url of the file.
     * @return {Promise}  A Promise storing the blob.
     */
    var loadBlob = function(url) {
        return new Promise(function(resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', url, true);
            xhr.responseType = 'blob';
            xhr.onload = function(e) {
                if (this.status == 200) {
                    var blob = this.response;
                    resolve(blob);
                } else reject(this.status);
            };
            xhr.send();
        });
    };

    /**
     * Sends data to the Python CherryPy server.
     * The FormData params should _exactly match_ the kwargs to the called CherryPy method.
     * For instance, for the Python method analyze(wavfile=None, transcript=None), you would write:
     * 		var fd = new FormData();
     *   	fd.append('wavfile', wavblob);
     *    	fd.append('transcript', transcript);
     * Example: sendFormData(fd, 'align').then(function(data){...});
     * @param  {FormData} formData The prepared data as a FormData object.
     * @param  {string}   suburl An sublocation within HOST, like 'align': localhost:8080/align
     * @return {Promise} A Promise handling the result of the AJAX call.
     */
    var sendFormData = function(formData, suburl) {
        return new Promise(function(resolve, reject) {
            $.ajax({
                type: 'POST',
                url: HOST + suburl,
                data: formData,
                processData: false,
                contentType: false
            }).done(function(data) {
                resolve(data);
            }).fail(function(xhr, err) {
                reject(err);
            });
        });
    };

    return pub;
}());

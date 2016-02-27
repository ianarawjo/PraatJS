form Extracts intensity contour from WAV file
	comment Input file path
	text input_wav
    comment Output file path
    text output_path
endform

Read from file... 'input_wav$'
To Intensity... 100.0 0.0 'yes'
selectObject: 2
Down to IntensityTier
selectObject: 3
Save as short text file... 'output_path$'
writeInfoLine: output_path$

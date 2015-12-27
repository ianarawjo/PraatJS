form Extracts pitch contour from WAV file
	comment Input file path
	text input_wav
    comment Output file path
    text output_path
endform

Read from file... 'input_wav$'
To Pitch... 0.001 75 600
selectObject: 2
Down to PitchTier
selectObject: 3
Save as short text file... output_path
writeInfoLine: output_path

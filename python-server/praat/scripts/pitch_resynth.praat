form Applies new pitch contour and saves resynthesized audio
	comment Input file path
	text input_wav
	comment The pitch tier file to apply
	text input_pitchtier
    comment The output file path
    text output_path
endform

Read from file... 'input_wav$'
To Manipulation... 0.001 75 600
Read from file... 'input_pitchtier$'
selectObject: 2
plusObject: 3
Replace pitch tier
Get resynthesis (PSOLA)
Write to WAV file... output_path
writeInfoLine: output_path

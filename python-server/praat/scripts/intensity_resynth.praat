form Applies new intensity contour and saves resynthesized audio
	comment Input file path
	text input_wav
	comment The intensity tier file to apply
	text input_tier
    comment The output file path
    text output_path
endform

Read from file... 'input_wav$'
Read from file... 'input_tier$'
selectObject: 1
plusObject: 2
Multiply
selectObject: 3
Write to WAV file... 'output_path$'
writeInfoLine: output_path$

form Applies new duration and saves resynthesized audio
	comment Input file path
	text input_wav
	comment The duration tier file to apply
	text input_durtier
    comment The output file path
    text output_path
endform

Read from file... 'input_wav$'
To Manipulation... 0.001 75 600
Read from file... 'input_durtier$'
selectObject: 2
plusObject: 3
Replace duration tier
selectObject: 2
Get resynthesis (PSOLA)
Write to WAV file... 'output_path$'
writeInfoLine: output_path$

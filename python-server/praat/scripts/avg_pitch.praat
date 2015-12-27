# This script measures pitch, intensity and formants every 10ms
# Written by Setsuko Shirai
# Contact ssetsuko@u.washington.edu
# ask a user the directories
form supply_arguments
	sentence input_file test.wav
	positive prediction_order 10
	positive minimum_pitch 75
	positive maximum_pitch 500
	positive new_sample_rate 11025
endform

Read from file... 'input_file$'

select all
numSelected = numberOfSelected ("Sound")

# change the name of each file - for batch processing
for i to numSelected
	select all
	currSoundID = selected ("Sound", i)
	select 'currSoundID'
	currName$ = "word_'i'"
	Rename... 'currName$'
endfor

for i to numSelected
	select Sound word_'i'
	# get the finishing time of the Sound file
	fTime = Get finishing time
      	# Use numTimes in the loop
	numTimes = fTime / 0.01
	newName$ = "word_'i'"
	select Sound word_'i'
      	# 1st argument: New sample rate 2nd argument: Precision (samples)
	Resample... 'new_sample_rate' 50
	# 1st argument: Time step (s), 2nd argument: Minimum pitch for Analysis,
	# 3rd argument: Maximum pitch for Analysis
	To Pitch... 0.01 'minimum_pitch' 'maximum_pitch'
	Rename... 'newName$'

	select Sound word_'i'_'new_sample_rate'
	To Intensity... 100 0

	select Sound word_'i'_'new_sample_rate'
	# 1st argument:  prediction order, 2nd argument: Analysis width (seconds)
	# 3rd argument: Time step (seconds),  4th argument: Pre-emphasis from (Hz)
	To LPC (autocorrelation)... prediction_order  0.025 0.005 50
	To Formant

    f0avg = 0
    pitchPoints = 0

	for itime to numTimes
		select Pitch word_'i'
		curtime = 0.01 * itime
		f0 = 0
		f0 = Get value at time... 'curtime' Hertz Linear
		f0$ = fixed$ (f0, 2)

		if f0$ = "--undefined--"
			f0$ = "0"
        else
            f0avg = f0avg + f0
            pitchPoints = pitchPoints + 1
		endif


		curtime$ = fixed$ (curtime, 5)

		select Intensity word_'i'_'new_sample_rate'
		intensity = Get value at time... 'curtime' Cubic


		intensity$ = fixed$ (intensity, 2)
		if intensity$ = "--undefined--"
			intensity$ = "0"
		endif

		select Formant word_'i'_'new_sample_rate'


		f1 = Get value at time... 1 'curtime' Hertz Linear
		f1$ = fixed$ (f1, 2)
		if f1$ = "--undefined--"
			f1$ = "0"
		endif

		f2 = Get value at time... 2 'curtime' Hertz Linear
		f2$ = fixed$ (f2, 2)
		if f2$ = "--undefined--"
			f2$ = "0"
		endif

		f3 = Get value at time... 3 'curtime' Hertz Linear
		f3$ = fixed$ (f3, 2)
		if f3$ = "--undefined--"
			f3$ = "0"
		endif

	endfor

    f0avg = f0avg / pitchPoints

    writeInfoLine: f0avg
endfor

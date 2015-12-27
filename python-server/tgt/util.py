# -*- coding: utf-8 -*-

# TextGridTools -- Read, write, and manipulate Praat TextGrid files
# Copyright (C) 2011-2014 Hendrik Buschmeier, Marcin Włodarczak
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division

import re
import collections
import copy

from .core import TextGrid, IntervalTier, Interval

##  High-level functions
##----------------------------------------------------------------------------

def shift_boundaries(tier, left, right):
    """
    Return a copy of the tier with boundaries shifted by the specified
    amount of time (in seconds). Positive values expand the tier and negative
    values shrink it, i.e.:
    * positive value of left shifts the left boundary to the left
    * negative value of left shifts the left boundary to the right
    * positive value of right shifts the right boundary to the right
    * negative value of right shifts the right boundary to the left.
    """

    tier_end_shifted = tier.end_time + left + right
    tier_shifted = IntervalTier(start_time=0,
                                end_time=tier_end_shifted,
                                name=tier.name)

    for i, interval in enumerate(tier.intervals):

        if interval.end_time <= left * -1:
            continue

        if interval.start_time > left * -1:
            interval_start_shifted = interval.start_time + left
        else:
            interval_start_shifted = 0

        interval_end_shifted = interval.end_time + left
        if (interval_start_shifted >= tier_end_shifted):
            break
        elif interval_end_shifted > tier_end_shifted:
            interval_end_shifted = tier_end_shifted

        tier_shifted.add_annotation(Interval(interval_start_shifted,
                                             interval_end_shifted,
                                             interval.text))
    return tier_shifted


def get_overlapping_intervals(tier1, tier2, regex=r'[^\s]+', overlap_label=None):
    '''Return a list of overlaps between intervals of tier1 and tier2.
    If no overlap_label is specified, concatenated labels
    of overlapping intervals are used as the resulting label.
    
    All nonempty intervals are included in the search by default.
    '''
    if not isinstance(tier2, IntervalTier):
        raise TypeError('Argument is not an IntervalTier')
    intervals1 = tier1.intervals
    intervals2 = tier2.intervals
    overlaps = []
    i, j = 0, 0
    while i < len(tier1) and j < len(tier2):
        lo = max(intervals1[i].start_time, intervals2[j].start_time)
        hi = min(intervals1[i].end_time, intervals2[j].end_time)
        if (lo < hi and re.search(regex, intervals1[i].text)
            and re.search(regex, intervals2[j].text)):
            if overlap_label is None:
                text = '+'.join([intervals1[i].text, intervals2[j].text])
            else:
                text = overlap_label
            overlaps.append(Interval(lo, hi, text))
        if intervals1[i].end_time < intervals2[j].end_time:
            i += 1
        else:
            j += 1
    return overlaps


def concatenate_textgrids(textgrids, ignore_nonmatching_tiers=False):
    '''Concatenate Tiers with matching names.

    TextGrids are concatenated in the order they are specified. If 
    ignore_nonmatching_tiers is False, an exception is raised if the
    number and the names of tiers differ between TextGrids.
    '''
    tier_names_intersection = set.intersection(
        *[set(tg.get_tier_names()) for tg in textgrids])
    # Check whether the TextGrids have the same number of tiers
    # and whether tier names match. If they don't
    # and if ignore_nonmatching_tiers is False, raise an exception.
    if (not ignore_nonmatching_tiers
        and not all([len(tier_names_intersection) == len(tg) for tg in textgrids])):
        raise Exception('TextGrids have different numbers of tiers or tier names do not match.')
    tot_duration = 0
    tiers = {}  # tier_name : tgt.Tier()
    for textgrid in textgrids:
        for tier in textgrid:
            if tier.name not in tier_names_intersection:
                continue
            intervals = []
            # If this is the first we see this tier, we just make a copy
            # of it as it is.
            if tier.name not in tiers.keys():
                tiers[tier.name] = copy.deepcopy(tier)
            # Otherwise we update the start and end times of intervals
            # and append them to the first part.
            else:
                for interval in tier.intervals:
                    interval.start_time += tot_duration
                    interval.end_time += tot_duration
                    intervals.append(interval)
                tiers[tier.name].add_annotations(intervals)
        tot_duration += textgrid.end_time
    # Create a new TextGrid and add the concatenated tiers
    textgrid_concatenated = TextGrid()
    # Add tiers in the order they're found in the first TextGrid.
    textgrid_concatenated.add_tiers(
        [tiers[x] for x in tier_names_intersection])
    return textgrid_concatenated


def merge_textgrids(textgrids, ignore_duplicates=True):
    '''Return a TextGrid object with tiers in all textgrids.p

    If ignore_duplicates is False, tiers with equal names are renamed
    by adding a path of the textgrid or a unique number incremented
    with each occurrence.
    '''
    tg_merged = TextGrid()
    tier_duplicates_lookup = collections.defaultdict(int)
    for tg in textgrids:
        for tier in tg:
            tier_copy = copy.deepcopy(tier)
            if tg_merged.has_tier(tier.name):
                if not ignore_duplicates:
                    if tg.filename.strip() != '':
                        tier_copy.name += '_' + tg.filename
                    else:
                        tier_duplicates_lookup[tier.name] += 1
                        tier_copy.name += '_' + str(tier_duplicates_lookup[tier.name])
                else:
                    continue
            tg_merged.add_tier(tier_copy)
    return tg_merged

## Chronogram
## ---------------------------------------------------------------------------

def chronogram(tiers, speech_label=None, silence_label=None):

    '''Construct a chronogram between intervals in input tiers.
    Interval labels are classified as silences or volcalisations
    by matching them against the speech_label and the silence_label
    regular expressions. By default all intervals with empty or
    whitespace-only labels are treated as silences.

    The code is a generalisation of Jaffe and Feldstein's (1970) 
    6-state Markov model to an arbitrary number of speakers. Instances
    of silences and overlaps are classified as within-speaker-overlap
    (wso), between-speaker-overlap (bso), within-speaker-silence (wss)
    or between-speaker-silence (bss).  Individual vocalistions are
    labelled with the the source tier name.
    '''
    

    # Calculate communicatfive states for each tier.
    communicative_states = classify_communicative_state(tiers, speech_label, silence_label)
    
    is_joint_state = lambda st: st == 'none' or st.find(',') > 0
    is_single_state = lambda st: not is_joint_state(st)

    chrono = IntervalTier(name='chronogram-{0}'.format('-'.join(t.name for t in tiers)))
    prev_single = None

    for i in range(len(communicative_states)):

        cur_start = communicative_states[i].start_time
        cur_end = communicative_states[i].end_time
        cur_state = communicative_states[i].text

        # Make sure there are no consecutive same state sequences
        if i > 0:
            prev_state = communicative_states[i - 1].text
            assert  prev_state != cur_state,\
                'Consecutive same states: {0}, {1}'.format(prev_state, cur_state)

        if is_joint_state(cur_state):

            # If we have not seen a single-speaker vocalisation, skip it.
            if  prev_single is None:
                continue

            try:
                next_state = communicative_states[i + 1].text
            except IndexError:
                next_state = None
            
            # Transitions between joint states do not result in speaker change.
            # The same is true for transitions from a joint state to a single state 
            # equal to the previous single state and for file-final joint states.
            if (next_state is None or is_joint_state(next_state)
                or (is_single_state(next_state) and prev_single == next_state)):

                chrono.add_interval(
                    Interval(start_time=cur_start, end_time=cur_end,
                             text='wso:{}'.format(cur_state) if cur_state != 'none' else 'wss'))
            else:
                chrono.add_interval(
                    Interval(start_time=cur_start, end_time=cur_end,
                             text='bso:{}'.format(cur_state) if cur_state != 'none' else 'bss'))
        # Label single vocalisations with the source tier name.
        elif is_single_state(cur_state):
            chrono.add_interval(Interval(start_time=cur_start, end_time=cur_end, text=cur_state))
            prev_single = cur_state
        else:
            raise Exception('Unknown cummunicative state: {0}'.format(cur_state))

    # FIXME: Should a dictionary with communicative labels and the chronogram be 
    # returned instead of the chronogram itself?
    # return {'communicative_labels': communicative_states, 'chronogram': chrono}
    return chrono

def communicative_labels(tiers, voc_re=None, silence_re=None):

    if silence_re is not None:
        speech_tiers = [t.name for t in tiers if re.search(silence_re, t[0].text) is None]
    else:
        if voc_re is None:
            voc_re = r'[^\s]+',
        speech_tiers = [t.name for t in tiers if re.search(voc_re, t[0].text) is not None]

    if not speech_tiers:
        return 'none'
    else:
        return ','.join(speech_tiers)

def classify_communicative_state(tiers, speech_label=None, silence_label=None):

    # Fill all gaps with empty intervals and ensure the tiers have
    # identical start and end times
    start_time_earliest = min(tier.start_time for tier in tiers)
    end_time_latest = max(tier.end_time for tier in tiers)

    tiers_filled = [tier.get_copy_with_gaps_filled(start_time=start_time_earliest,
                                                   end_time=end_time_latest)
                    for tier in tiers]

    communicative_states = IntervalTier(name='communicative_states')


    while all(tiers_filled):
        lo = max(x[0].start_time for x in tiers_filled)
        hi = min(x[0].end_time for x in tiers_filled)
        
        if lo < hi:
            com_state = communicative_labels(tiers_filled, speech_label, silence_label)
            communicative_states.add_annotation(Interval(lo, hi, com_state))

        for t in tiers_filled:
            if t[0].end_time == hi:
                del t[0]

    # Merge consecutive intervals with indentical labels
    communicative_states = communicative_states.get_copy_with_same_intervals_merged()
    return communicative_states

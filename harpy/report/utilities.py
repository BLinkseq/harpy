import json
import os
from io import StringIO
from typing import Literal

import numpy as np
import polars as pl

from harpy.common.file_ops import safe_read


class StopExecution(Exception):
    '''An exception type to prematurely end a notebook without it being considered an error'''
    def _render_traceback_(self):
        return []

def extract_metric(x: list[str], param: str):
    '''Convenience function to find the relevnant sections of the bcftools.stats file and return a table'''
    selectiontext = "".join(s for s in x if s.startswith(f"{param}\t"))
    if not selectiontext:
        return pl.DataFrame()
    try:
        return pl.read_csv(
            StringIO(selectiontext), separator="\t", has_header=False,
            infer_schema_length=None, null_values=["nan", "-nan"]
        )
    except pl.exceptions.NoDataError:
        return pl.DataFrame()

def last_line(filename: str) -> str:
    '''Returns the last line of a file. Automatically handles gzip if file ends with case-insensitive `.gz`'''
    with safe_read(filename) as f:
        last_line = None
        for line in f:
            last_line = line
        return last_line.strip()

def nxx(lengths: list[int] | pl.Series, X: int = 50) -> int:
    '''
    Calculate and return the NX value of a list of numbers, where `X` is
    the kind of NX value you want. For example, `X=50` would return the `N50`.
    '''
    threshold = sum(lengths) * (X / 100)
    if isinstance(lengths, pl.Series):
        _l = lengths.to_list()
    else:
        _l = list(lengths)
    _l.sort(reverse=True)
    cum_sum = 0
    for i in _l:
        cum_sum += i
        if cum_sum >= threshold:
            return i
    return max(lengths)


def binned_histogram(data: pl.Series, bin_size: int|float, normalize: bool = False, max_val: int|float|None = None, precision = 2) -> pl.DataFrame:
    '''
    Calculates a binned histogram of counts from the input `data` for bins of size `bin_size`
    with columns ['bin','interval','count']. If `normalize=True`, returns a DataFrame with columns ['bin','interval', 'proportion'].
    '''
    col_max: float | int = (data.max() or 0) if max_val is None else max_val
    #col_max: float | int = int(data.max()) if max_val is None else max_val
    bins = np.arange(0, col_max + bin_size, bin_size).round(precision)
    #bins = np.arange(0, col_max + (3 * bin_size), bin_size).round(precision)

    labels: list[str] = [f"{round(i, precision)}-{round(i + bin_size, precision)}" for i in bins]

    # Cut into bins using searchsorted
    bin_indices = np.searchsorted(bins, data.to_numpy(), side='left') - 1
    bin_indices = np.clip(bin_indices, 0, len(bins) - 2)

    colname: Literal['count', 'proportion'] = 'proportion' if normalize else 'count'

    counts = np.bincount(bin_indices, minlength=len(bins) - 1).astype(float)
    values = counts / counts.sum() if normalize else counts

    return pl.DataFrame({
        'bin': bins[:-1].astype(str),
        'interval': labels[:-1],
        colname: values
    })

def consolidated_hist(data: pl.Series, linkmask: pl.Series, binwidth: int|float, normalize: bool) -> pl.DataFrame:
    '''
    Invoke `binned_histogram()` once for all the data (a column) and linked-read only data, returning a single DataFrame
    with cumulative sum columns. The `linkmask` is a boolean list/series that subsets `data`. Both `nmol` and
    `nlinkmol` are necessary to correctly calculate proportions.
    '''
    shared_max = max(float(data.max()), float(data.filter(linkmask).max()))
    binned_df = binned_histogram(data, binwidth, normalize, max_val = shared_max).rename({'proportion': 'all reads'})
    binned_dfl = binned_histogram(data.filter(linkmask), binwidth, normalize, max_val = shared_max)
    binned_df = binned_df.with_columns([
        binned_dfl['proportion'].alias('linked reads'),
        binned_df['all reads'].cum_sum().alias('all reads (cumsum)'),
        binned_dfl['proportion'].cum_sum().alias('linked reads (cumsum)'),
    ])
    if isinstance(binwidth, int):
        labels = [
            f"{int(float(i))}-{int(float(i)) + binwidth - 1}"
            for i in binned_df["bin"].to_list()
        ]
        #labels = [f"{i}-{int(i)+binwidth-1}" for i in binned_df['bin'].to_list()]
    else:
        digits = len(str(binwidth).split(".")[1])
        labels = [f"{i}-{round(float(i)+binwidth,digits)}" for i in binned_df['bin'].to_list()]
    binned_df = binned_df.with_columns(pl.Series('range_label', labels))
    return binned_df

def trunc_digits(x: float,y: int) -> float:
  '''Trucate the input float `x` at decimal digit `y` without rounding'''
  return float(f"%.{y}f" % x)

def human_format(num):
    match num:
        case num if num >= 1e9:
            return f"{num/1e9:.2f}G"
        case num if num >= 1e6:
            return f"{num/1e6:.2f}M"
        case num if num >= 1e3:
            return f"{num/1e3:.2f}K"
        case _:
            return str(num)

import json
import os
from pathlib import Path
import polars as pl

from harpy.report.utilities import nxx


## SAMTOOLS PARSERS -----------------------------
_keys_to_keep = set([
    "percentage_of_properly_paired_reads_(%)",
    "pairs_on_different_chromosomes",
    "reads_mapped_%",
    "reads_QC_failed_%",
    "error_rate",
    "supplementary_alignments",
    "raw_total_sequences",
    "insert_size_average",
    'self_&_mate_mapped_%'
])

def _get_val(x: str):
    '''Return the value of the line `x` as an int'''
    return int(x.strip().split(": ")[-1])

def parse_samtools_stats(indir: str, datatype: str):
    """Find Samtools stats logs in indir and parse their data, returning a polars dataframe"""
    statsdir = os.path.join(indir, "samtools_stats")
    markdupdir = os.path.join(indir, "markdup")
    samtools_stats = {}
    
    for f in Path(statsdir).glob(f"*{datatype}.stats"):
        samplename = f.stem.removesuffix(f".{datatype}")
        file_contents = f.read_text().splitlines()
        parsed_data = _parse_SN(file_contents)
        pcr, optical = _parse_markdup(os.path.join(markdupdir, f"{samplename}.markdup"))

        if len(parsed_data) > 0:
            # Work out some percentages
            if "raw_total_sequences" in parsed_data:
                seqs = parsed_data.get("sequences", 0)
                mapped_and_paired = parsed_data.get("reads_mapped_and_paired", 0)
                parsed_data['self_&_mate_mapped_%'] = round((mapped_and_paired / seqs) * 100, 1) if seqs > 0 else 0
                parsed_data['error_rate'] = round(parsed_data['error_rate'] * 100, 5)
                for k in list(parsed_data.keys()):
                    if k.startswith("reads_") and k != "raw_total_sequences" and parsed_data["raw_total_sequences"] > 0:
                        parsed_data[f"{k}_%"] = round((parsed_data[k] / parsed_data["raw_total_sequences"]) * 100, 2)
                        del parsed_data[k]
            samtools_stats[samplename] = {
                key.replace("_", " ").replace(" and ", " & ").replace("reads", "").title().strip():
                parsed_data.get(key, 0) for key in _keys_to_keep
            }
            samtools_stats[samplename]["% Duplicates (PCR)"] = pcr
            samtools_stats[samplename]["% Duplicates (Opt)"] = optical
    if len(samtools_stats) == 0:
        return pl.DataFrame()
    
    df = pl.DataFrame([{"Sample": sample, **cols} for sample, cols in samtools_stats.items()]).rename({
        "Self & Mate Mapped %": "% Self+Mate Mapped",
        "Qc Failed %": "% QC Failed",
        "Raw Total Sequences": "Total Reads",
        "Insert Size Average": "Average Insert (bp)",
        "Percentage Of Properly Paired  (%)": "% Properly Paired",
        "Pairs On Different Chromosomes": "Diff Chromosome",
        "Mapped %": "% Mapped",
        "Error Rate": "Error Rate (%)",
        "Supplementary Alignments": "Supp Alignments"    
    }).select([
        "Sample",
        "Total Reads",
        "% Mapped",
        "% Properly Paired",
        "% Self+Mate Mapped",
        "% Duplicates (PCR)",
        "% Duplicates (Opt)",
        "Average Insert (bp)",
        "% QC Failed",
        "Diff Chromosome",
        "Error Rate (%)",
        "Supp Alignments",
    ])
    df = df.with_columns(
        pl.col("Average Insert (bp)").round(0).cast(pl.Int32),
        pl.col("Total Reads").cast(pl.Int64),
        pl.col("Diff Chromosome").cast(pl.Int64),
        pl.col("Supp Alignments").cast(pl.Int64)
    )
    return df

def _parse_markdup(filename):
    '''Parses a samtools markdup output log file and returns the percent of duplicates as a tuple (pcr, optical)'''
    pcr = 0
    optical = 0
    reads = 0
    with open(filename, 'r') as f:
        for line in f:
            if line.startswith("READ:"):
                reads = _get_val(line)
            if line.startswith("DUPLICATE PAIR:") or line.startswith("DUPLICATE SINGLE:"):
                pcr += _get_val(line)
            if line.startswith("DUPLICATE PAIR OPTICAL:") or line.startswith("DUPLICATE SINGLE OPTICAL:"):
                optical += _get_val(line)
    if reads <= 0:
        return 0.0, 0.0
    pcr_perc = round(((pcr-optical) / reads) * 100, 2)
    optical_perc = round((optical / reads) * 100, 2)
    return pcr_perc, optical_perc

def _parse_SN(filecontents: list[str]):
    """
    Parse `SN` rows from samtools stats output into a normalized dict.
    Also extract samtools and htslib versions if present on the header line.
    Returns a tuple: (parsed_data, samtools_version, htslib_version)
    """
    parsed_data = {}
    for line in filecontents:
        if not line.startswith("SN"):
            if line.startswith("# First Fragment Qualities."):
                break
            continue
        sections = line.split("\t")
        if len(sections) < 3:
            continue
        field = sections[1].strip()[:-1].replace(" ", "_").lstrip()
        try:
            value = float(sections[2].strip())
        except ValueError:
            continue
        parsed_data[field] = value
    return parsed_data

## Parse djinn sam stats output -------------------
DJINNSAMSTATSSCHEMA = {
    "Sample": pl.String,
    "Fragments": pl.Int64,
    "Valid": pl.Float64,
    "Linked": pl.Float64,
    "Barcodes": pl.Int64,
    "Unique Molecules": pl.Int64,
    "Molecules/Barcode": pl.Float64,
    "Fragments/Molecule": pl.Float64,
    "Insert Molecule Coverage": pl.Float64,
    "Exact Molecule Coverage": pl.Float64,
    "N50": pl.Int64,
    "N75": pl.Int64,
    "N90": pl.Int64,
}

def _parse_djinn_sam_stats_single(infile: str) -> dict:
    sample = os.path.basename(infile).removesuffix(".lrstats.gz")
    tb = pl.read_csv(infile, separator="\t", schema_overrides={"contig": pl.String})

    valid = tb.filter(pl.col("molecule") != "invalid")
    multi = valid.filter(pl.col("fragments") >= 2)

    tot_frags = tb["fragments"].sum()
    if tot_frags == 0:
        return {k: 0 for k in DJINNSAMSTATSSCHEMA} | {"Sample": sample}

    n_mol = valid.height
    n_bx = tb["molecule"].str.replace(r"-\d+$", "").n_unique()
    lens = multi["length_inferred"].sort(descending=True)

    return {
        "Sample": sample,
        "Fragments": tot_frags,
        "Valid": round(valid["fragments"].sum() / tot_frags, 4),
        "Linked": round(multi["fragments"].sum() / tot_frags, 4),
        "Barcodes": n_bx,
        "Unique Molecules": n_mol,
        "Molecules/Barcode": round(n_mol / n_bx, 2),
        "Fragments/Molecule": round(multi["fragments"].mean() or 0, 1),
        "Insert Molecule Coverage": round(multi["coverage_inserts"].mean() or 0, 2),
        "Exact Molecule Coverage": round(multi["coverage_bp"].mean() or 0, 2),
        **{f"N{p}": (nxx(lens, p) if multi.height else 0) for p in (50, 75, 90)},
    }


def parse_djinn_sam_stats(infiles: list[str]) -> pl.DataFrame:
    """Parse a list of lrstats.gz files resulting from djinn sam stats and return a polars dataframe"""
    records = [_parse_djinn_sam_stats_single(f) for f in infiles]
    return (
        pl.DataFrame(records, schema=DJINNSAMSTATSSCHEMA)
        .fill_nan(0)
        .fill_null(0)
        .sort("Sample")
    )



## FASTP results parser ---------------

class FastpResults:
    def __init__(self, report_dir):
        '''Collect all JSON report files'''
        stats = {
            "Sample"         : [],
            "Reads (Before)" : [],
            "Reads (After)"  : [],
            "Bases (Before)" : [],
            "Bases (After)"  : [],
            "% Q20 (Before)" : [],
            "% Q20 (After)"  : [],
            "% Q30 (Before)" : [],
            "% Q30 (After)"  : [],
            "% GC (Before)"  : [],
            "% GC (After)"   : []
        }
        mean_qual_curves = {"before" : {}, "after" : {}}
        self.max_len = 0
        self.max_len_after = 0
        gc_curves = {"before" : {}, "after" : {}}
        mean_qual_curves_r2 = {"before" : {}, "after" : {}}
        self.max_len_r2 = 0
        self.max_len_r2_after = 0
        gc_curves_r2 = {"before" : {}, "after" : {}}
        json_files = [f for f in os.listdir(report_dir) if f.endswith('.json')]
        self.samples = len(json_files)
        for jf in json_files:
            path = os.path.join(report_dir, jf)
            samplename = jf.replace('.fastp.json', '')
            with open(path) as f:
                data = json.load(f)
                summary = data.get('summary', {})
                before = summary.get('before_filtering', {})
                after = summary.get('after_filtering', {})

                # Extract quality and GC curves for read1
                qual_curve_before = data.get('read1_before_filtering', {}).get('quality_curves', {}).get('mean', [])
                qual_curve_after = data.get('read1_after_filtering', {}).get('quality_curves', {}).get('mean', [])
                gc_curve_before = data.get('read1_before_filtering', {}).get('content_curves', {}).get('GC', [])
                gc_curve_after = data.get('read1_after_filtering', {}).get('content_curves', {}).get('GC', [])
                mean_qual_curves["before"][samplename] = qual_curve_before
                mean_qual_curves["after"][samplename] = qual_curve_after
                gc_curves["before"][samplename] = gc_curve_before
                gc_curves["after"][samplename] = gc_curve_after

                self.max_len = max(self.max_len, len(qual_curve_before))
                self.max_len_after = max(len(qual_curve_after), self.max_len_after)

                # Extract quality and GC curves for read2 if present
                qual_curve_before_r2 = data.get('read2_before_filtering', {}).get('quality_curves', {}).get('mean', [])
                qual_curve_after_r2 = data.get('read2_after_filtering', {}).get('quality_curves', {}).get('mean', [])
                gc_curve_before_r2 = data.get('read2_before_filtering', {}).get('content_curves', {}).get('GC', [])
                gc_curve_after_r2 = data.get('read2_after_filtering', {}).get('content_curves', {}).get('GC', [])
                if qual_curve_before_r2 or qual_curve_after_r2 or gc_curve_before_r2 or gc_curve_after_r2:
                    mean_qual_curves_r2["before"][samplename] = qual_curve_before_r2
                    mean_qual_curves_r2["after"][samplename] = qual_curve_after_r2
                    gc_curves_r2["before"][samplename] = gc_curve_before_r2
                    gc_curves_r2["after"][samplename] = gc_curve_after_r2

                    self.max_len_r2 = max(len(qual_curve_before_r2), self.max_len_r2)
                    self.max_len_r2_after = max(len(qual_curve_after_r2), self.max_len_r2_after)

                    stats["Sample"].append(jf.replace('.fastp.json', ''))
                    stats["Reads (Before)"].append(before.get('total_reads', 0))
                    stats["Reads (After)"].append(after.get('total_reads', 0))
                    stats["Bases (Before)"].append(before.get('total_bases', 0))
                    stats["Bases (After)"].append(after.get('total_bases', 0))
                    stats["% Q20 (Before)"].append(round(before.get('q20_rate', 0) * 100, 2))
                    stats["% Q20 (After)"].append(round(after.get('q20_rate', 0) * 100, 2))
                    stats["% Q30 (Before)"].append(round(before.get('q30_rate', 0) * 100, 2))
                    stats["% Q30 (After)"].append(round(after.get('q30_rate', 0) * 100, 2))
                    stats["% GC (Before)"].append(round(before.get('gc_content', 0) * 100, 2))
                    stats["% GC (After)"].append(round(after.get('gc_content', 0) * 100, 2))

        self.stats =  pl.DataFrame(stats)
        self.qual_curves = pl.DataFrame(mean_qual_curves["before"])
        self.qual_curves_after = pl.DataFrame(mean_qual_curves["after"])
        self.qual_curves_r2 = pl.DataFrame(mean_qual_curves_r2["before"])
        self.qual_curves_r2_after = pl.DataFrame(mean_qual_curves_r2["after"])
        self.gc_curves = pl.DataFrame(gc_curves["before"])
        self.gc_curves_after = pl.DataFrame(gc_curves["after"])
        self.gc_curves_r2 = pl.DataFrame(gc_curves_r2["before"])
        self.gc_curves_r2_after = pl.DataFrame(gc_curves_r2["after"])


## Preproc GIH parsers -------------
def read_count_hist(infile: str) -> pl.DataFrame:
    return (
        pl.scan_csv(infile, separator="\t", has_header=False,
                    schema={"bc": pl.String, "count": pl.Int64})
        .select("count")
        .group_by("count").len()
        .sort("count", descending=True)
        .collect(engine="streaming")
    )


## SV output parsers ------------------
#for i in infiles:
_sv_coltypes = {'contig': pl.String, 'Chr1': pl.String, 'Chr2' : pl.String}
_sv_types = {"INV": "Inversion", "DEL": "Deletion", "DUP": "Duplication", "BND": "Breakend"}

def parse_naibr_leviathan_SVs(infiles: list[str]):
    """Read in and standardize the bedpe files generated by leviathan and naibr"""
    _infiles = [f for f in infiles if os.path.getsize(f)]
    if not _infiles:
        return None
    sv = pl.read_csv(
        _infiles,
        separator = "\t",
        schema_overrides = _sv_coltypes,
        infer_schema_length = None,
    )

    # standardize the column names btwn Leviathan and Naibr
    if "Break1" in sv.columns:
        sv = sv.drop("Chr2")
        sv.columns = ["Sample", "Contig", "Start", "End", 'Split Mol', 'Discordant', 'Orientation', 'Haplotype', 'Score', 'Filter', 'Type']
        sv = sv.select(['Sample', 'Contig', 'Start', 'End', 'Type', 'Split Mol', 'Discordant', 'Orientation', 'Haplotype', 'Score', 'Filter'])
        sv = sv.with_columns(pl.col('Type').str.to_lowercase().str.to_titlecase())
    else:
        sv.columns = [i.replace("position_", "").replace("_", " ").title() for i in sv.columns]
        sv = sv.with_columns(pl.col('Type').replace_strict(_sv_types))
    
    return sv

def process_variants(df: pl.DataFrame, bin_size: int = 50) -> pl.DataFrame:
    """Group variants by binning positions into windows"""
    return (
        df.group_by(
            'Contig', 'Type',
            start_bin=(pl.col('Start') // bin_size) * bin_size,
            end_bin=(pl.col('End') // bin_size) * bin_size,
        )
        .agg(
            pl.col('Start').median().cast(pl.Int64),
            pl.col('End').median().cast(pl.Int64),
            pl.col('Sample').count().alias('N Samples'),
            pl.col('Sample').alias('Samples'),
        )
        .sort('Contig', 'Type', 'start_bin', 'end_bin')
        .select('Contig', 'Start', 'End', 'Type', 'N Samples', 'Samples')
    )

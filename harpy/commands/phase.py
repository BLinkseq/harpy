"""Harpy haplotype phasing workflow"""

import os

import rich_click as click

from harpy.common.cli_filetypes import FASTAfile, HPCProfile, SAMfile, VCFfile
from harpy.common.cli_params import ContigList, HapCutParams, WhatshapParams, SnakemakeParams
from harpy.common.system_ops import container_ok
from harpy.runtime.workflow import Workflow
from harpy.validation.fasta import FASTA
from harpy.validation.populations import Populations
from harpy.validation.vcf import VCF
from harpy.validation.xam import XAM

@click.group()
@click.help_option('--help', hidden = True)
def phase():
    """
    Phase SNPs or alignments

    Provide an additional subcommand `snp` or `bam` for more information the phasing workflows.
    """

@click.command(no_args_is_help = True, context_settings={"allow_interspersed_args" : False}, epilog = "Documentation: https://blinkseq.github.io/harpy/commands/phase")
@click.option('-x', '--extra-params', panel = "Parameters", type = WhatshapParams(), help = 'Additional whatshap haplotag parameters, in quotes')
@click.option('-d', '--molecule-distance', panel = "Parameters", default = 100000, show_default = True, type = click.IntRange(min = 100), help = 'Distance cutoff to split molecules (bp)')
@click.option('-n', '--ploidy', panel = "Parameters", default = 2, show_default = True, type=click.IntRange(min=1), help = 'Ploidy of samples')
@click.option('-V', '--vcf-samples', panel = "Parameters", is_flag = True, show_default = True, default = False, help = 'Use samples present in vcf file for phasing rather than those found in the inputs')
@click.option('-U','--unlinked', panel = "Parameters", is_flag = True, default = False, help = "Treat input data as not linked reads")
@click.option('--clean', hidden = True, panel = "Workflow Options", type = str, help = 'Delete the log (`l`), .snakemake (`s`), and/or workflow (`w`) folders when done')
@click.option('-T', '--no-temp', hidden = True, panel = "Workflow Options", is_flag = True, default = False, help = 'Don\'t delete temporary files')
@click.option('-C', '--container', panel = "Workflow Options",  is_flag = True, default = False, help = 'Use a container instead of conda', callback=container_ok)
@click.option('-H', '--hpc', panel = "Workflow Options",  type = HPCProfile(), help = 'HPC submission YAML configuration file')
@click.option('-O', '--output', panel = "Workflow Options", type = click.Path(exists = False, resolve_path = True), default = "Phase/bam", show_default=True,  help = 'Output directory name')
@click.option('-Q', '--quiet', panel = "Workflow Options", default = 0, type = click.IntRange(0,2,clamp=True), help = '`0` all output, `1` progress bar, `2` no output')
@click.option('-N', '--setup', panel = "Workflow Options",  is_flag = True, hidden = True, default = False, help = 'Setup the workflow and exit')
@click.option('-S', '--snakemake', panel = "Workflow Options", type = SnakemakeParams(), help = 'Additional Snakemake parameters, in quotes')
@click.option('-@', '--threads', panel = "Workflow Options", default = 4, show_default = True, type = click.IntRange(3, 999, clamp = True), help = 'Number of threads to use')
@click.help_option('--help', hidden = True)
@click.argument('reference',required = True, type=FASTAfile(), nargs = 1)
@click.argument('vcf', required = True, type = VCFfile(), nargs = 1)
@click.argument('inputs', required=True, type=SAMfile(), nargs=-1)
def bam(vcf, inputs, output, threads, unlinked, vcf_samples, molecule_distance, ploidy, reference, snakemake, extra_params, quiet, hpc, clean, container, setup, no_temp):
    """
    Phase alignments using phased SNPs

    Provide the reference fasta, then a **phased** vcf file followed by the input alignment (`.bam`) files and/or directories at the end of the command as
    individual files/folders, using shell wildcards (e.g. `data/myotis*.bam`), or both.

    Presence and type of linked-read data is auto-detected, but you may choose to omit barcode
    information with `-U`. Use `--vcf-samples` to phase only the samples present in your input
    `VCF` file rather than all the samples present in the `INPUTS` alignments.
    """
    workflow = Workflow("phase_bam", "phase_bam.smk", output, container, clean, quiet)
    workflow.setup_snakemake(threads, hpc, snakemake, no_temp)
    workflow.conda = ["phase"]

    ## checks and validations ##
    alignments = XAM(inputs, detect_bc= not unlinked, quiet = quiet)
    vcffile = VCF(vcf, workflow.workflow_directory, quiet = quiet, threads = threads)
    vcffile.check_phase()
    vcffile.match_samples(alignments.files, vcf_samples)
    if vcf_samples:
        alignments.filter(vcffile.samples)
    fasta = FASTA(reference, quiet)

    workflow.linkedreads["type"] = alignments.lr_type
    workflow.input(vcffile.file, "vcf")
    workflow.input(fasta.file, "reference")
    workflow.input(alignments.files, "alignments")
    workflow.param(molecule_distance, "distance-threshold")
    workflow.param(ploidy, "ploidy")
    workflow.param(vcf_samples, "prioritize-vcf-samples")
    workflow.param(alignments.lr_type != "none", "use-linked-info")
    if extra_params:
        workflow.param(extra_params, "extra")

    workflow.info = {
        "Input VCF": os.path.basename(vcffile.file),
        "Samples": min(len(vcffile.samples), alignments.count),
        "Barcode Type": alignments.lr_type,
        **({'Reference': os.path.basename(reference)} if reference else {}),
        "Output Folder": os.path.relpath(output) + "/"
    }

    workflow.initialize(setup)

@click.command(no_args_is_help = True, context_settings={"allow_interspersed_args" : False}, epilog = "Documentation: https://blinkseq.github.io/harpy/commands/phase")
@click.option('-x', '--extra-params', panel = "Parameters", type = HapCutParams(), help = 'Additional HapCut2 parameters, in quotes')
@click.option('-m', '--min-base-quality', panel = "Parameters", default = 13, show_default = True, type = click.IntRange(0, 100, clamp = True), help = 'Minimum base quality for phasing')
@click.option('-q', '--min-map-quality', panel = "Parameters", default = 20, show_default = True, type = click.IntRange(0, 40, clamp = True), help = 'Minimum mapping quality for phasing')
@click.option('-d', '--molecule-distance', panel = "Parameters", default = 100000, show_default = True, type = click.IntRange(min = 100), help = 'Distance cutoff to split molecules (bp)')
@click.option('-p', '--populations', panel = "Parameters", type=click.Path(exists = True, dir_okay=False, readable=True, resolve_path=True), help = 'File of `sample`_\\<TAB\\>_`population` for secondary phasing')
@click.option('-t', '--prune-threshold', panel = "Parameters", default = 30, show_default = True, type = click.IntRange(0,100, clamp = True), help = 'PHRED-scale threshold (%) for pruning low-confidence SNPs (larger prunes more.)')
@click.option('-r', '--reference', panel = "Parameters", type=FASTAfile(), help = 'Path to reference genome if wanting to also extract reads spanning indels')
@click.option('-U', '--unlinked', panel = "Parameters", is_flag = True, default = False, help = "Treat input data as not linked reads")
@click.option('-V', '--vcf-samples', panel = "Parameters", is_flag = True, show_default = True, default = False, help = 'Use samples present in vcf file for phasing rather than those found in the inputs')
@click.option('-C', '--container', panel = "Workflow Options",  is_flag = True, default = False, help = 'Use a container instead of conda', callback=container_ok)
@click.option('--contigs', panel = "Workflow Options",  type = ContigList(), help = 'File or list of contigs to plot')
@click.option('-H', '--hpc', panel = "Workflow Options",  type = HPCProfile(), help = 'HPC submission YAML configuration file')
@click.option('-O', '--output', panel = "Workflow Options", type = click.Path(exists = False, resolve_path = True), default = "Phase/snp", show_default=True,  help = 'Output directory name')
@click.option('-Q', '--quiet', panel = "Workflow Options", default = 0, type = click.IntRange(0,2,clamp=True), help = '`0` all output, `1` progress bar, `2` no output')
@click.option('-N', '--setup', panel = "Workflow Options",  is_flag = True, hidden = True, default = False, help = 'Setup the workflow and exit')
@click.option('-@', '--threads', panel = "Workflow Options", default = 4, show_default = True, type = click.IntRange(2, 999, clamp = True), help = 'Number of threads to use')
@click.option('-R', '--skip-reports', panel = "Workflow Options",  is_flag = True, show_default = True, default = False, help = 'Don\'t generate HTML reports')
@click.option('-S', '--snakemake', panel = "Workflow Options", type = SnakemakeParams(), help = 'Additional Snakemake parameters, in quotes')
@click.option('-T', '--no-temp', hidden = True, panel = "Workflow Options", is_flag = True, default = False, help = 'Don\'t delete temporary files')
@click.option('--clean', hidden = True, panel = "Workflow Options", type = str, help = 'Delete the log (`l`), .snakemake (`s`), and/or workflow (`w`) folders when done')
@click.help_option('--help', hidden = True)
@click.argument('vcf', required = True, type = VCFfile(), nargs = 1)
@click.argument('inputs', required=True, type=SAMfile(), nargs=-1)
def snp(vcf, inputs, output, threads, unlinked, min_map_quality, min_base_quality, molecule_distance, prune_threshold, vcf_samples, reference, populations, snakemake, extra_params, skip_reports, quiet, hpc, clean, container, contigs, setup, no_temp):
    """
    Phase SNPs into haplotypes

    Provide the vcf file followed by the input alignment (`.bam`) files and/or directories at the end of the command as
    individual files/folders, using shell wildcards (e.g. `data/myotis*.bam`), or both.

    Presence and type of linked-read data is auto-detected, but you may choose to omit barcode
    information with `-U`. Use `--vcf-samples` to phase only the samples present in your input
    `VCF` file rather than all the samples present in the `INPUTS` alignments. Optionally specify
    `--populations` for a second round of statistical phasing by population.
    """
    workflow = Workflow("phase_snp", "phase_snp.smk", output, container, clean, quiet)
    workflow.setup_snakemake(threads, hpc, snakemake, no_temp)
    workflow.notebook_files = ["hapcut.ipynb"]
    workflow.conda = ["phase"]

    ## checks and validations ##
    alignments = XAM(inputs, detect_bc= not unlinked, quiet = quiet)
    vcffile = VCF(vcf, workflow.workflow_directory, quiet = quiet, threads = threads)
    vcffile.match_samples(alignments.files, vcf_samples)
    if contigs:
        vcffile.match_contigs(contigs)
    if vcf_samples:
        alignments.filter(vcffile.samples)

    workflow.linkedreads["type"] = alignments.lr_type
    workflow.notebooks["skip"] = skip_reports
    workflow.notebooks["plot-contigs"] = contigs if contigs else "default"
    workflow.input(vcffile.file, "vcf")
    if reference:
        fasta = FASTA(reference, quiet)
        workflow.input(fasta.file, "reference")
    if populations:
        popfile = Populations(populations, alignments.files, quiet)
        popfile.copy_to_workflow(output)
        workflow.input(popfile.file, "groupings:source")
        workflow.input("workflow/sample.groups", "groupings:processed")
    workflow.input(alignments.files, "alignments")
    workflow.param(prune_threshold, "prune")
    workflow.param(min_map_quality, "min-map-quality")
    workflow.param(min_base_quality, "min-base-quality")
    workflow.param(molecule_distance, "distance-threshold")
    workflow.param(vcf_samples, "prioritize-vcf-samples")
    if extra_params:
        workflow.param(extra_params, "extra")

    workflow.info = {
        "Input VCF": os.path.basename(vcffile.file),
        "Samples" : min(len(vcffile.samples), alignments.count),
        "Barcode Type" : alignments.lr_type,
        "Phase Indels" : "yes" if reference else "no",
        **({'Reference': os.path.basename(reference)} if reference else {}),
        "Secondary Phasing" : "yes" if populations else "no",
        "Output Folder": os.path.relpath(output) + "/"
    }

    workflow.initialize(setup)

phase.add_command(bam)
phase.add_command(snp)

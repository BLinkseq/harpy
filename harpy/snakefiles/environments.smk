from harpy.common.environments import HarpyEnvs
from harpy import __version__

localrules: all, conda_env

envs = list(HarpyEnvs().environments().keys())

rule all:
    input:
        collect("{conda}.env", conda = config.get("envs", envs))

rule conda_env:
    output: "{conda}.env"
    conda: "envs/{conda}.yaml"
    container: "ghcr.io/blinkseq/harpy:{conda}_" + __version__
    shell: "touch {output}"



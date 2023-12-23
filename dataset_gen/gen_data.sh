#!/bin/bash
#SBATCH -p chaos
#SBATCH -A shared-sml-staff
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=5
#SBATCH --job-name=gendata
#SBATCH -t 1-00
#SBATCH --output=/nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/gen_data.txt
#SBATCH --error=//nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/gen_data.txt
#SBATCH --ntasks=1
#SBATCH -N 1


set -e 
export PATH="/nfs/data_chaos/sazzolin/miniconda3/bin:$PATH"
eval "$(conda shell.bash hook)"
conda activate dignn_2.1.1_1.7.2

# python gen_struc.py --global_b "0.33"
python gen_struc.py --global_b "0.6"
python gen_struc.py --global_b "0.9"

python gen_mixed.py --global_b "0.33"
python gen_mixed.py --global_b "0.6"
python gen_mixed.py --global_b "0.9"

echo DONE
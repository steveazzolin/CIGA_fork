#!/bin/bash
#SBATCH -p chaos
#SBATCH -A shared-sml-staff
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=10
#SBATCH --job-name=spmotif
#SBATCH -t 1-00
#SBATCH --output=/nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/run_spmotif.txt
#SBATCH --error=//nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/run_spmotif.txt
#SBATCH --ntasks=1
#SBATCH -N 1


set -e 
export PATH="/nfs/data_chaos/sazzolin/miniconda3/bin:$PATH"
eval "$(conda shell.bash hook)"
conda activate dignn_2.1.1_1.7.2


python main.py  -c_in 'feat' -c_rep 'feat'  --seed '[1,2,3,4,5]' --num_layers 3 --dataset 'SPMotif' --bias 0.33 --r 0.25 --contrast 8 --spu_coe 0 --model 'gcn' --dropout 0.


echo DONE
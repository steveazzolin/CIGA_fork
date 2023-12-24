#!/bin/bash
#SBATCH -p chaos
#SBATCH -A shared-sml-staff
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --job-name=mspmotif
#SBATCH -t 1-00
#SBATCH --output=/nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/run_mspmotif.txt
#SBATCH --error=//nfs/data_chaos/sazzolin/sedignn/CIGA_fork/sbatch_outputs/run_mspmotif.txt
#SBATCH --ntasks=1
#SBATCH -N 1


set -e 
export PATH="/nfs/data_chaos/sazzolin/miniconda3/bin:$PATH"
eval "$(conda shell.bash hook)"
conda activate dignn_2.1.1_1.7.2

#CIGAV1
for bias in 0.33 0.6 0.9; do
    python main.py  \
        -c_in 'feat' \
        -c_rep 'feat'  \
        --seed '[1,2]' \
        --num_layers 3 \
        --dataset 'mSPMotif' \
        --bias ${bias} \
        --r 0.25 \
        --contrast 8 \
        --spu_coe 0 \
        --model 'gcn' \
        --dropout 0. \
        --batch_size 128 \
        --log_wandb
done

#CIGAV2
for bias in 0.33 0.6 0.9; do
    python main.py  \
        -c_in 'feat' \
        -c_rep 'feat'  \
        --seed '[1,2]' \
        --num_layers 3 \
        --dataset 'mSPMotif' \
        --bias ${bias} \
        --r 0.25 \
        --contrast 8 \
        --spu_coe 1 \
        --model 'gcn' \
        --dropout 0.  \
        --batch_size 128 \
        --log_wandb
done

echo DONE
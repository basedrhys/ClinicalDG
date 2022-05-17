python -m clinicaldg.scripts.train \
    --output_dir /scratch/rc4499/thesis/output \
    --wandb_name $1 \
    --es_method train \
    --algorithm ERM \
    --max_steps 20000 \
    --checkpoint_freq 500 \
    --train_env_0 $2 \
    --train_env_1 $3 \
    --val_env $4 \
    --test_env $5 \
    --balance_method $6 \
    --resample_method $7 \
    --hparams '{"batch_size": 128, "lr": 0.00005}'

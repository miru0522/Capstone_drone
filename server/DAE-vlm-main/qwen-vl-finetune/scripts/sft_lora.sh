#!/bin/bash

# Distributed training configuration
MASTER_ADDR=${MASTER_ADDR:-"127.0.0.1"}
MASTER_PORT=${MASTER_PORT:-$(shuf -i 20001-29999 -n 1)}
NNODES=${WORLD_SIZE:-1}
NPROC_PER_NODE=$(nvidia-smi --list-gpus |wc -l)

# DeepSpeed configuration
deepspeed=./zero3.json # zero3_offload.json

# Model configuration
llm=Qwen/Qwen2.5-VL-3B-Instruct  # Using HuggingFace model ID

# Training hyperparameters
lr=2e-5
batch_size=1
grad_accum_steps=1

# Training entry point
entry_file=../qwenvl/train/train_qwen_lora.py

# Dataset configuration (replace with public dataset names)
datasets="a_n"

# Output configuration
run_name="qwen2_5vl-baseline"
output_dir=./outputs

# Training arguments
args="--deepspeed ${deepspeed} \
    --model_name_or_path "${llm}" \
    --dataset_use ${datasets} \
    --data_flatten True \
    --tune_mm_vision False \
    --tune_mm_mlp True \
    --tune_mm_llm True \
    --bf16 \
    --output_dir ${output_dir} \
    --num_train_epochs 1 \
    --per_device_train_batch_size ${batch_size} \
    --gradient_accumulation_steps ${grad_accum_steps} \
    --max_pixels 50176 \
    --min_pixels 784 \
    --eval_strategy "no" \
    --save_strategy "no" \
    --save_total_limit 1 \
    --learning_rate ${lr} \
    --weight_decay 0 \
    --warmup_ratio 0.03 \
    --max_grad_norm 1 \
    --lr_scheduler_type "cosine" \
    --logging_steps 1 \
    --model_max_length 8192 \
    --gradient_checkpointing True \
    --dataloader_num_workers 0 \
    --run_name ${run_name}"

# Launch training
torchrun --nproc_per_node=${NPROC_PER_NODE} \
         --master_addr=${MASTER_ADDR} \
         --master_port=${MASTER_PORT} \
         ../qwenvl/train/train_qwen_lora.py \
         --deepspeed ${deepspeed} \
         --model_name_or_path "${llm}" \
         --dataset_use ${datasets} \
         --data_flatten True \
         --tune_mm_vision False \
         --tune_mm_mlp True \
         --tune_mm_llm True \
         --bf16 \
         --output_dir ${output_dir} \
         --num_train_epochs 1 \
         --per_device_train_batch_size ${batch_size} \
         --gradient_accumulation_steps ${grad_accum_steps} \
         --max_pixels 50176 \
         --min_pixels 784 \
         --eval_strategy "no" \
         --save_strategy "epoch" \
         --save_total_limit 1 \
         --learning_rate ${lr} \
         --weight_decay 0 \
         --warmup_ratio 0.03 \
         --max_grad_norm 1 \
         --lr_scheduler_type "cosine" \
         --logging_steps 1 \
         --model_max_length 8192 \
         --gradient_checkpointing True \
         --dataloader_num_workers 0 \
         --run_name ${run_name} \
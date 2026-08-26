import re

# Define placeholders for dataset paths
ASSAULT = {
    "annotation_path": "/tf/notebook/NFS_dataset/Qwen2.5-VL/qwen-vl-finetune/qwenvl/train_dataset/assault_train.json",
    "data_path": "/tf/notebook/NFS_dataset/YOLO_with_ReID/results/video_group_1(only day)"
}

A_N = {
    "annotation_path": "/tf/notebook/NFS_dataset/Qwen2.5-VL/qwen-vl-finetune/qwenvl/train_dataset/merged_a_n_train.json",
    "data_path": "/tf/notebook/NFS_dataset/YOLO_with_ReID/results/video_group_1(only day)"
}
ASSAULT_SWOON = {
    "annotation_path": "/tf/notebook/NFS_dataset/Qwen2.5-VL/qwen-vl-finetune/qwenvl/train_dataset/merged_a_n_train.json",
    "data_path": "/tf/notebook/NFS_dataset/YOLO_with_ReID/results/video_group_1(only day)"
}

data_dict = {
    # "assault" : ASSAULT,
    #"a_n" : A_N,
    "a_s" : ASSAULT_SWOON
}


def parse_sampling_rate(dataset_name):
    match = re.search(r"%(\d+)$", dataset_name)
    if match:
        return int(match.group(1)) / 100.0
    return 1.0


def data_list(dataset_names):
    config_list = []
    for dataset_name in dataset_names:
        sampling_rate = parse_sampling_rate(dataset_name)
        dataset_name = re.sub(r"%(\d+)$", "", dataset_name)
        if dataset_name in data_dict.keys():
            config = data_dict[dataset_name].copy()
            config["sampling_rate"] = sampling_rate
            config_list.append(config)
        else:
            raise ValueError(f"do not find {dataset_name}")
    return config_list


if __name__ == "__main__":
    dataset_names = ["a_s%100"]
    configs = data_list(dataset_names)
    for config in configs:
        print(config)

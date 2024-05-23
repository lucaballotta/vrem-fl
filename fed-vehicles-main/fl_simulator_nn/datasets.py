import os
import pickle
import string
from pathlib import Path

import torch
from torchvision.datasets import CIFAR10, CIFAR100, EMNIST
from torchvision.transforms import Compose, ToTensor, Normalize
from torch.utils.data import Dataset

import numpy as np
from PIL import Image


class ApolloscapeDataset(Dataset):

    def __init__(self,
                 road_record_list,
                 base_dir='./',
                 debug=False):

        """

            :param road_record_list: it is a dictionary with the fields 'road' (string) and 'record' (list),
            e.g., {'road' : 'road02_ins', 'record' : [1, 5, 21]}.

            Data is taken from the camera 5

        """
        n_classes = 36
        self.void_classes = [0, 1, 255, 98, 99, 100]
        self.valid_classes = [[17], [33, 161, 38, 166, 39, 167], [34, 162, 35, 163, 40, 168], [36, 164], [37, 165],
                              [49], [50], [65, 66, 67], [81, 82, 83, 84, 85, 86], [97], [113]]
        class_map_tmp = dict(zip(range(n_classes), self.valid_classes))
        self.n_classes = len(class_map_tmp)
        self.class_map = dict()
        for key, value in class_map_tmp.items():
            for elem in value:
                self.class_map[elem] = key
        self.debug = debug
        self.base_dir = Path(base_dir)
        self.ignore_index = 255
        self.img_paths = []
        self.lbl_paths = []

        for road_record in road_record_list:
            self.road_dir = self.base_dir / Path(road_record['road'])
            self.record_list = road_record['record']

            for record in self.record_list:
                img_paths_tmp = self.road_dir.glob(f'ColorImage/Record{record:03}/Camera5/*.jpg')
                lbl_paths_tmp = self.road_dir.glob(f'Label/Record{record:03}/Camera5/*.png')

                img_paths_basenames = {Path(img_path.name).stem for img_path in img_paths_tmp}
                lbl_paths_basenames = {Path(lbl_path.name).stem.replace('_bin', '') for lbl_path in lbl_paths_tmp}

                intersection_basenames = img_paths_basenames & lbl_paths_basenames

                img_paths_intersection = [
                    self.road_dir / Path(f'ColorImage/Record{record:03}/Camera5/{intersection_basename}.jpg')
                    for intersection_basename in intersection_basenames]
                lbl_paths_intersection = [
                    self.road_dir / Path(f'Label/Record{record:03}/Camera5/{intersection_basename}_bin.png')
                    for intersection_basename in intersection_basenames]

                self.img_paths += img_paths_intersection
                self.lbl_paths += lbl_paths_intersection

        self.img_paths.sort()
        self.lbl_paths.sort()

        assert len(self.img_paths) == len(self.lbl_paths)

        self.img_transformer = Compose([ToTensor(),
                                        Normalize(mean=[0.485, 0.456, 0.406],
                                                  std=[0.229, 0.224, 0.225])])
        self.lbl_transformer = torch.LongTensor

    def __len__(self):
        return len(self.img_paths)

    def __getitem__(self, index):
        img_path = self.img_paths[index]
        lbl_path = self.lbl_paths[index]

        img = np.array(Image.open(img_path))
        lbl = np.array(Image.open(lbl_path))
        for c in self.void_classes:
            lbl[lbl == c] = self.ignore_index
        for c in self.valid_classes:
            for elem in c:
                lbl[lbl == elem] = self.class_map[elem]

        lbl = lbl[:, :, 0]

        if self.debug:
            print(np.unique(lbl))
        else:
            img = self.img_transformer(img)
            lbl = self.lbl_transformer(lbl)

        return img, lbl, img_path.stem


class TabularDataset(Dataset):
    """
    Constructs a torch.utils.Dataset object from a pickle file;
    expects pickle file stores tuples of the form (x, y) where x is vector and y is a scalar

    Attributes
    ----------
    data: iterable of tuples (x, y)

    Methods
    -------
    __init__
    __len__
    __getitem__

    """

    def __init__(self, path):
        """
        :param path: path to .pkl file

        """
        with open(path, "rb") as f:
            self.data = pickle.load(f)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        x, y = self.data[idx]
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.int64), idx


class SubFEMNIST(Dataset):
    """
    Constructs a subset of FEMNIST dataset corresponding to one client;
    Initialized with the path to a `.pt` file;
    `.pt` file is expected to hold a tuple of tensors (data, targets) storing the images and there corresponding labels.

    Attributes
    ----------
    transform
    data: iterable of integers
    targets

    Methods
    -------
    __init__
    __len__
    __getitem__

    """

    def __init__(self, path):
        self.transform = Compose([
            ToTensor(),
            Normalize((0.1307,), (0.3081,))
        ])

        self.data, self.targets = torch.load(path)

    def __len__(self):
        return self.data.size(0)

    def __getitem__(self, index):
        img, target = self.data[index], int(self.targets[index])

        img = np.uint8(img.numpy() * 255)
        img = Image.fromarray(img, mode='L')

        if self.transform is not None:
            img = self.transform(img)

        return img, target, index


class SubEMNIST(Dataset):
    """
    Constructs a subset of EMNIST dataset from a pickle file;
    expects pickle file to store list of indices

    Attributes
    ----------
    indices: iterable of integers
    transform
    data
    targets

    Methods
    -------
    __init__
    __len__
    __getitem__

    """

    def __init__(self, path, emnist_data=None, emnist_targets=None, transform=None):
        """

        :param path: path to .pkl file; expected to store list of indices
        :param emnist_data: EMNIST dataset inputs
        :param emnist_targets: EMNIST dataset labels
        :param transform:

        """
        with open(path, "rb") as f:
            self.indices = pickle.load(f)

        if transform is None:
            self.transform = \
                Compose([
                    ToTensor(),
                    Normalize((0.1307,), (0.3081,))
                ])

        if emnist_data is None or emnist_targets is None:
            self.data, self.targets = get_emnist()
        else:
            self.data, self.targets = emnist_data, emnist_targets

        self.data = self.data[self.indices]
        self.targets = self.targets[self.indices]

    def __len__(self):
        return self.data.size(0)

    def __getitem__(self, index):
        img, target = self.data[index], int(self.targets[index])

        img = Image.fromarray(img.numpy(), mode='L')

        if self.transform is not None:
            img = self.transform(img)

        return img, target, index


class SubCIFAR10(Dataset):
    """
    Constructs a subset of CIFAR10 dataset from a pickle file;
    expects pickle file to store list of indices

    Attributes
    ----------
    indices: iterable of integers
    transform
    data
    targets

    Methods
    -------
    __init__
    __len__
    __getitem__

    """

    def __init__(self, path, cifar10_data=None, cifar10_targets=None, transform=None):
        """

        :param path: path to .pkl file; expected to store list of indices
        :param cifar10_data: Cifar-10 dataset inputs stored as torch.tensor
        :param cifar10_targets: Cifar-10 dataset labels stored as torch.tensor
        :param transform:

        """
        with open(path, "rb") as f:
            self.indices = pickle.load(f)

        if transform is None:
            self.transform = \
                Compose([
                    ToTensor(),
                    Normalize(
                        (0.4914, 0.4822, 0.4465),
                        (0.2023, 0.1994, 0.2010)
                    )
                ])

        if cifar10_data is None or cifar10_targets is None:
            self.data, self.targets = get_cifar10()
        else:
            self.data, self.targets = cifar10_data, cifar10_targets

        self.data = self.data[self.indices]
        self.targets = self.targets[self.indices]

    def __len__(self):
        return self.data.size(0)

    def __getitem__(self, index):
        img, target = self.data[index], self.targets[index]

        img = Image.fromarray(img.numpy())

        if self.transform is not None:
            img = self.transform(img)

        target = target

        return img, target, index


class SubCIFAR100(Dataset):
    """
    Constructs a subset of CIFAR100 dataset from a pickle file;
    expects pickle file to store list of indices

    Attributes
    ----------
    indices: iterable of integers
    transform
    data
    targets

    Methods
    -------
    __init__
    __len__
    __getitem__

    """

    def __init__(self, path, cifar100_data=None, cifar100_targets=None, transform=None):
        """

        :param path: path to .pkl file; expected to store list of indices:
        :param cifar100_data: CIFAR-100 dataset inputs
        :param cifar100_targets: CIFAR-100 dataset labels
        :param transform:

        """
        with open(path, "rb") as f:
            self.indices = pickle.load(f)

        if transform is None:
            self.transform = \
                Compose([
                    ToTensor(),
                    Normalize(
                        (0.4914, 0.4822, 0.4465),
                        (0.2023, 0.1994, 0.2010)
                    )
                ])

        if cifar100_data is None or cifar100_targets is None:
            self.data, self.targets = get_cifar100()

        else:
            self.data, self.targets = cifar100_data, cifar100_targets

        self.data = self.data[self.indices]
        self.targets = self.targets[self.indices]

    def __len__(self):
        return self.data.size(0)

    def __getitem__(self, index):
        img, target = self.data[index], self.targets[index]

        img = Image.fromarray(img.numpy())

        if self.transform is not None:
            img = self.transform(img)

        target = target

        return img, target, index


class CharacterDataset(Dataset):
    def __init__(self, file_path, chunk_len):
        """
        Dataset for next character prediction, each sample represents an input sequence of characters
         and a target sequence of characters representing to next sequence of the input

        :param file_path: path to .txt file containing the training corpus
        :param chunk_len: (int) the length of the input and target sequences

        """
        self.all_characters = string.printable
        self.vocab_size = len(self.all_characters)
        self.n_characters = len(self.all_characters)
        self.chunk_len = chunk_len

        with open(file_path, 'r') as f:
            self.text = f.read()

        self.tokenized_text = torch.zeros(len(self.text), dtype=torch.long)

        self.inputs = torch.zeros(self.__len__(), self.chunk_len, dtype=torch.long)
        self.targets = torch.zeros(self.__len__(), self.chunk_len, dtype=torch.long)

        self.__build_mapping()
        self.__tokenize()
        self.__preprocess_data()

    def __tokenize(self):
        for ii, char in enumerate(self.text):
            self.tokenized_text[ii] = self.char2idx[char]

    def __build_mapping(self):
        self.char2idx = dict()
        for ii, char in enumerate(self.all_characters):
            self.char2idx[char] = ii

    def __preprocess_data(self):
        for idx in range(self.__len__()):
            self.inputs[idx] = self.tokenized_text[idx:idx + self.chunk_len]
            self.targets[idx] = self.tokenized_text[idx + 1:idx + self.chunk_len + 1]

    def __len__(self):
        return max(0, len(self.text) - self.chunk_len)

    def __getitem__(self, idx):
        return self.inputs[idx], self.targets[idx], idx


def get_emnist():
    """
    gets full (both train and test) EMNIST dataset inputs and labels;
    the dataset should be first downloaded (see data/emnist/README.md)

    :return:
        emnist_data, emnist_targets

    """
    emnist_path = os.path.join("data", "emnist", "raw_data")
    assert os.path.isdir(emnist_path), "Download EMNIST dataset!!"

    emnist_train = \
        EMNIST(
            root=emnist_path,
            split="byclass",
            download=True,
            train=True
        )

    emnist_test = \
        EMNIST(
            root=emnist_path,
            split="byclass",
            download=True,
            train=True
        )

    emnist_data = \
        torch.cat([
            emnist_train.data,
            emnist_test.data
        ])

    emnist_targets = \
        torch.cat([
            emnist_train.targets,
            emnist_test.targets
        ])

    return emnist_data, emnist_targets


def get_cifar10():
    """
    gets full (both train and test) CIFAR10 dataset inputs and labels;
    the dataset should be first downloaded (see data/emnist/README.md)

    :return:
        cifar10_data, cifar10_targets

    """
    cifar10_path = os.path.join("data", "cifar10", "raw_data")
    assert os.path.isdir(cifar10_path), "Download cifar10 dataset!!"

    cifar10_train = \
        CIFAR10(
            root=cifar10_path,
            train=True, download=False
        )

    cifar10_test = \
        CIFAR10(
            root=cifar10_path,
            train=False,
            download=False)

    cifar10_data = \
        torch.cat([
            torch.tensor(cifar10_train.data),
            torch.tensor(cifar10_test.data)
        ])

    cifar10_targets = \
        torch.cat([
            torch.tensor(cifar10_train.targets),
            torch.tensor(cifar10_test.targets)
        ])

    return cifar10_data, cifar10_targets


def get_cifar100():
    """
    gets full (both train and test) CIFAR100 dataset inputs and labels;
    the dataset should be first downloaded (see data/cifar100/README.md)

    :return:
        cifar100_data, cifar100_targets

    """

    cifar100_path = os.path.join("data", "cifar100", "raw_data")
    assert os.path.isdir(cifar100_path), "Download cifar10 dataset!!"

    cifar100_train = \
        CIFAR100(
            root=cifar100_path,
            train=True, download=False
        )

    cifar100_test = \
        CIFAR100(
            root=cifar100_path,
            train=False,
            download=False)

    cifar100_data = \
        torch.cat([
            torch.tensor(cifar100_train.data),
            torch.tensor(cifar100_test.data)
        ])

    cifar100_targets = \
        torch.cat([
            torch.tensor(cifar100_train.targets),
            torch.tensor(cifar100_test.targets)
        ])

    return cifar100_data, cifar100_targets

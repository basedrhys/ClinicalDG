import torch
import os
import numpy as np
from PIL import Image
from clinicaldg.cxr import Constants, process
import pandas as pd
from torchvision import transforms
import pickle
from pathlib import Path
from torch.utils.data import Dataset, ConcatDataset
from time import sleep

def get_dataset(dfs_all, img_size, envs = [], split = None, only_frontal = True, imagenet_norm = True, augment = 0, cache = False, subset_label = None):
      
    if split in ['val', 'test']:
        assert(augment in [0, -1])
    
    if augment == 1: # image augmentations
        image_transforms = [transforms.RandomHorizontalFlip(), 
                            transforms.RandomRotation(10),     
                            # transforms.RandomResizedCrop(size = img_size, scale = (0.75, 1.0)),
                        transforms.ToTensor()]
    elif augment == 0: 
        image_transforms = [transforms.ToTensor()]
    elif augment == -1: # only resize, just return a dataset with PIL images; don't ToTensor()
        image_transforms = []        
   
    if imagenet_norm and augment != -1:
        image_transforms.append(transforms.Normalize(Constants.IMAGENET_MEAN, Constants.IMAGENET_STD))             
    
    datasets = []
    for e in envs:        
        if split is not None:    
            splits = [split]
        else:
            splits = ['train', 'val', 'test']
            
        dfs = [dfs_all[e][i] for i in splits]        
            
        for c, s in enumerate(splits):
            cache_dir = Path(Constants.cache_dir)/ f'{e}/'
            cache_dir.mkdir(parents=True, exist_ok=True)
            datasets.append(AllDatasetsShared(dfs[c], img_size, transform = transforms.Compose(image_transforms)
                                      , split = split, cache = cache, cache_dir = cache_dir, subset_label = subset_label)) 
                
    if len(datasets) == 0:
        return None
    elif len(datasets) == 1:
        ds = datasets[0]
    else:
        ds = ConcatDataset(datasets)
        ds.dataframe = pd.concat([i.dataframe for i in datasets])
    
    return ds

class AllDatasetsShared(Dataset):
    def __init__(self, dataframe, img_size, transform=None, split = None, cache = True, cache_dir = '', subset_label = None):
        super().__init__()
        self.dataframe = dataframe
        self.dataset_size = self.dataframe.shape[0]
        self.transform = transform
        self.split = split
        self.cache = cache
        self.cache_dir = Path(cache_dir)
        self.subset_label = subset_label # (str) select one label instead of returning all Constants.take_labels
        self.img_size=img_size

        resize_trnf = [transforms.Resize(size = [self.img_size, self.img_size])]
        # if self.img_size < 224:
            # resize_trnf.append(transforms.Resize(size = [256, 256]))
        self.resize_trnf = transforms.Compose(resize_trnf)

        print("Built resize transform:", self.resize_trnf)

        print(f"Created dataset with subset label={self.subset_label}, images of size={self.img_size}")

    def get_cache_path(self, cache_dir, meta):
        path = Path(meta['path'])
        if meta['env'] in ['PAD', 'NIH']:
            return cache_dir / (path.stem + '.pkl')
        elif meta['env'] in ['MIMIC', 'CXP']:
            return (cache_dir / '_'.join(path.parts[-3:])).with_suffix('.pkl')  

    def load_image(self, path): # TODO check this is the only error spot
        wait_time = 1
        num_tries = 5
        for _ in range(num_tries):
            try:
                img = np.array(Image.open(path))
                return img
            except Exception as e:
                print(e)
                print("Trying to read file again")
                sleep(wait_time)

        return None

        
    def __getitem__(self, idx):
        item = self.dataframe.iloc[idx]
        cache_path = self.get_cache_path(self.cache_dir, item)
        
        if self.cache and cache_path.is_file():
            img, label, meta = pickle.load(cache_path.open('rb'))
            meta = item.to_dict()
        else:            
            img = self.load_image(item["path"])

            if img is None:
                return self.__getitem__(0)

            if img.dtype == 'int32':
                img = np.uint8(img/(2**16)*255)
            elif img.dtype == 'bool':
                img = np.uint8(img)
            else: #uint8
                pass

            if len(img.shape) == 2:
                img = img[:, :, np.newaxis]
                img = np.concatenate([img, img, img], axis=2)            
            elif len(img.shape)>2:
                img = img[:,:,0]
                img = img[:, :, np.newaxis]
                img = np.concatenate([img, img, img], axis=2) 

            img = Image.fromarray(img)

            # pad_len = 224 - self.img_size
            # if pad_len > 0:
            #     side_pad_len = int(pad_len / 2)
            #     tmp_transforms.append(transforms.Pad(side_pad_len))
            img = self.resize_trnf(img)
            disease_labels = Constants.take_labels + ["All"]
            label = torch.FloatTensor(np.zeros(len(disease_labels), dtype=float))
            for i in range(0, len(disease_labels)):
                val = self.dataframe[disease_labels[i].strip()].iloc[idx]
                if not (isinstance(val, int) or isinstance(val, float)):
                    val = val.astype('float')
                if (val > 0):
                    label[i] = val

            meta = item.to_dict()
            
            if self.cache:
                pickle.dump((img, label, meta), cache_path.open('wb'))
        
        if self.transform is not None: # apply image augmentations after caching
            img = self.transform(img)
        
        # Apply the actual label
        if self.subset_label:
            label = int(label[disease_labels.index(self.subset_label)])
        
        return img, label, meta
            

    def __len__(self):
        return self.dataset_size

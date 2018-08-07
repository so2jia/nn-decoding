This repository contains analysis code for the paper:

*Does the brain represent words? An evaluation of brain decoding studies of
language understanding.* {Jon Gauthier and Anna Ivanova}. [2018 Conference on
Cognitive Computational Neuroscience][2].

Our study combines imaging data from [Pereira et al. (2018)][1] with various
pretrained computational models. See the section ["Using the encoding
models"](#using-the-encoding-models) for information about using these models
to encode novel stimuli.

This repository is open-source under the MIT License. If you would like to
reuse our code or otherwise extend our work, please cite our paper:

     @inproceedings{gauthier2018does,
       title={Does the brain represent words? An evaluation of brain decoding studies of language understanding.},
       author={Gauthier, Jon and Ivanova, Anna},
       booktitle={Conference on Cognitive Computational Neuroscience},
       year={2018}
     }

## Requirements

- Python 3
- numpy
- scikit-learn
- Jupyter Lab / Notebook
- matplotlib
- pandas
- tqdm

## Reproducing our results

This repository contains pre-computed target representations from the seven
models tested in the paper. The remaining necessary analysis steps are as
follows:

1. Fetch the public data of [Pereira et al. (2018)][1] using the script
   `fetch_data.sh` (requires TODO GB of disk space).
2. Use `learn_decoder.py` to learn decoders from subject fMRI data to each of
   the target representations (stored in the `encodings` directory):

       for encoding in baseline dissent.books8.epoch9 fairseq.wmt14.en-fr.fconv imdbsentiment infersent.allnli order-embeddings skipthought; do
           python learn_decoder.py data/stimuli_384sentences.txt encodings/384sentences.${encoding.npy} data \
               --encoding_project 256 --out_path perf.${encoding}.csv
       done
3. Open `analysis.ipynb` with Jupyter and re-run all cells, changing references
   to the output `perf.*.csv` files if necessary. The notebook renders
   per-subject performance graphs for each learned decoder, along with a
   summary graph (Figure 2 of the paper).
4. Use `heatmap.py` to build the model regression heatmap, saving a file
   `heatmap.svg` (Figure 3) and numerical data `heatmap.csv`:

       python heatmap.py encodings/384sentences.{baseline,dissent.books8.epoch9,fairseq.wmt14.en-fr.fconv,imdbsentiment,infersent.allnli,order-embeddings,skipthought}.npy

## Using the encoding models

We forked seven open-source NLP models and modified their processing code to
simply output the intermediate representations of their inputs. The target
encodings were generated by running each of these forked models on the 384
sentences in `data/384sentences.txt` (available after running `fetch_data.sh`).

We plan to make the modified model scripts available in the near future, so
that researchers can compute representations for their own test stimuli under
the same framework. (If you're interested in a short-term solution, please
ask!)


[1]: TODO
[2]: https://ccneuro.org/2018/Default.asp

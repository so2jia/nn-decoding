"""
Data analysis tools shared across scripts and notebooks.
"""

from collections import defaultdict
import itertools
import logging
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg", warn=False)
import numpy as np
import pandas as pd
import seaborn as sns
import scipy.io as io
import scipy.stats as st
from sklearn.decomposition import PCA
from tqdm import tqdm

L = logging.getLogger(__name__)


def load_sentences(sentence_path="data/sentences/stimuli_384sentences.txt"):
    with open(sentence_path, "r") as f:
        sentences = [line.strip() for line in f]
    return sentences


def load_encodings(paths, project=None):
  encodings = []
  for encoding_path in paths:
    encodings_i = np.load(encoding_path)
    L.info("%s: Loaded encodings of size %s.", encoding_path, encodings_i.shape)

    if project is not None:
      L.info("Projecting encodings to dimension %i with PCA", project)

      if encodings_i.shape[1] < project:
        L.warn("Encodings are already below requested dimensionality: %i < %i"
                    % (encodings_i.shape[1], project))
      else:
        pca = PCA(project).fit(encodings_i)
        L.info("PCA explained variance: %f", sum(pca.explained_variance_ratio_) * 100)
        encodings_i = pca.transform(encodings_i)

    encodings.append(encodings_i)

  encodings = np.concatenate(encodings, axis=1)
  return encodings


def load_brain_data(path, project=None):
  subject_data = io.loadmat(path)
  subject_images = subject_data["examples"]
  if project is not None:
    L.info("Projecting brain images to dimension %i with PCA", project)
    if subject_images.shape[1] < project:
      L.warn("Images are already below requested dimensionality: %i < %i"
             % (subject_images.shape[1], project))
    else:
      pca = PCA(project).fit(subject_images)
      L.info("PCA explained variance: %f", sum(pca.explained_variance_ratio_) * 100)
      subject_images = pca.transform(subject_images)

  return subject_images


def load_decoding_perfs(results_dir):
    """
    Load and render a DataFrame describing decoding performance across models,
    model runs, and subjects.

    Args:
        results_dir: path to pipeline decoder output directory
    """

    results = {}
    result_keys = ["model", "run", "step", "subject"]
    for csv in tqdm(list(Path(results_dir).glob("**/*.csv")),
                    desc="Loading perf files"):
      key = get_decoder_id(csv.parent.name)
      try:
        df = pd.read_csv(csv, usecols=["mse", "r2",
                                       "rank_median", "rank_mean",
                                       "rank_min", "rank_max"])
      except ValueError:
        continue
        
      results[key] = df
    
    if len(results) == 0:
        raise ValueError("No valid csv outputs found.")
    
    ret = pd.concat(results, names=result_keys)
    # drop irrelevant CSV row ID level
    ret.index = ret.index.droplevel(-1)
    return ret


def load_decoding_preds(results_dir, glob_prefix=None):
    """
    Load decoder predictions into a dictionary organized by decoder properties:
    decoder target model, target model run, target model run training step,
    and source subject image.
    """
    decoder_re = re.compile(r"\.(\w+)-run(\d+)-(\d+)-([\w\d]+)\.pred\.npy$")
    
    results = {}
    for npy in tqdm(list(Path(results_dir).glob("%s*.pred.npy" % (glob_prefix or ""))),
                    desc="Loading prediction files"):
        model, run, step, subject = decoder_re.findall(npy.name)[0]
        results[model, int(run), int(step), subject] = np.load(npy)
        
    if len(results) == 0:
        raise ValueError("No valid npy pred files found.")
        
    return results
  
  
def get_encoding_ckpt_id(encoding_dir):
    """
    Get information about a model encoding from its output directory name.
    """
    encoding_dir = encoding_dir.name if isinstance(encoding_dir, Path) else encoding_dir
    try:
      model, run, step = re.findall(r"^([\w_]+)-(\d+)-(\d+)$", encoding_dir)[0]
    except IndexError:
      raise ValueError("Failed to extract checkpoint information from encoding directory %s" % encoding_dir)
      
    return model, int(run), int(step)
  
  
def get_decoder_id(decoder_dir):
    """
    Get information about a learned decoder from its output directory name.
    """
    decoder_dir = decoder_dir.name if isinstance(decoder_dir, Path) else decoder_dir
    model, run, step, subject = re.findall("^([\w_]+)-(\d+)-(\d+)-([\w\d]+)$", decoder_dir)[0]
    return model, int(run), int(step), subject


def eval_ranks(Y_pred, idxs, encodings, encodings_normed=True):
  """
  Run a rank evaluation on predicted encodings `Y_pred` with dataset indices
  `idxs`.

  Args:
    Y_pred: `N_test * n_dim`-matrix of predicted encodings for some
      `N_test`-subset of sentences
    idxs: `N_test`-length array of dataset indices generating each of `Y_pred`
    encodings: `M * n_dim`-matrix of dataset encodings. The perfect decoder
      would predict `Y_pred[idxs] == encoding[idxs]`.

  Returns:
    ranks: `N_test * M` integer matrix. Each row specifies a
      ranking over sentences computed using the decoding model, given the
      brain image corresponding to each row of Y_test_idxs.
    rank_of_correct: `N_test` array indicating the rank of the target
      concept for each test input.
  """
  N_test = len(Y_pred)
  assert N_test == len(idxs)

  # TODO implicitly coupled to decoder normalization -- best to factor this
  # out!
  if encodings_normed:
    Y_pred -= Y_pred.mean(axis=0)
    Y_pred /= np.linalg.norm(Y_pred, axis=1, keepdims=True)

  # For each Y_pred, evaluate rank of corresponding Y_test example among the
  # entire collection of Ys (not just Y_test), where rank is established by
  # cosine distance.
  # n_Y_test * n_sentences
  similarities = np.dot(Y_pred, encodings.T)

  # Calculate distance ranks across rows.
  orders = (-similarities).argsort(axis=1)
  ranks = orders.argsort(axis=1)
  # Find the rank of the desired vectors.
  ranks_test = ranks[np.arange(len(idxs)), idxs]

  return ranks, ranks_test


def wilcoxon_rank_preds(models, correct_bonferroni=True, pairs=None):
    """
    Run Wilcoxon rank tests comparing the ranks of correct sentence representations in predictions
    from two or more models.
    """
    if pairs is None:
        pairs = list(itertools.combinations(models.keys(), 2))

    model_preds = {model: pd.read_csv("perf.384sentences.%s.pred.csv" % path).sort_index()
                   for model, path in models.items()}

    subjects = next(iter(model_preds.values())).subject.unique()

    results = {}
    for model1, model2 in pairs:
        m1_preds, m2_preds = model_preds[model1], model_preds[model2]
        m_preds = m1_preds.join(m2_preds["rank"], rsuffix="_m2")
        pair_results = m_preds.groupby("subject").apply(lambda xs: st.wilcoxon(xs["rank"], xs["rank_m2"])) \
            .apply(lambda ys: pd.Series(ys, index=("w_stat", "p_val")))

        results[model1, model2] = pair_results

    results = pd.concat(results, names=["model1", "model2"]).sort_index()

    if correct_bonferroni:
        correction = len(results)
        print(0.01 / correction, len(results))
        results["p_val_corrected"] = results.p_val * correction

    return results


def load_bert_finetune_metadata(savedir, checkpoint_step=None):
    """
    Load metadata for an instance of a finetuned BERT model.
    """
    savedir = Path(savedir)

    import tensorflow as tf
    from tensorflow.python.pywrap_tensorflow import NewCheckpointReader
    try:
        ckpt = NewCheckpointReader(str(savedir / "model.ckpt"))
    except tf.errors.NotFoundError:
        if checkpoint_step is None:
            raise
        ckpt = NewCheckpointReader(str(savedir / ("model.ckpt-step%i" % checkpoint_step)))

    ret = {}
    try:
        ret["global_steps"] = ckpt.get_tensor("global_step")
        ret["output_dims"] = ckpt.get_tensor("output_bias").shape[0]
    except tf.errors.NotFoundError:
        ret.setdefault("global_steps", np.nan)
        ret.setdefault("output_dims", np.nan)

    ret["steps"] = defaultdict(dict)

    # Load training events data.
    try:
        events_file = next(savedir.glob("events.*"))
    except StopIteration:
        # no events data -- skip
        print("Missing training events file in savedir:", savedir)
        pass
    else:
        total_global_norm = 0.
        first_loss, cur_loss = None, None
        tags = set()
        for e in tf.train.summary_iterator(str(events_file)):
            for v in e.summary.value:
                tags.add(v.tag)
                if v.tag == "grads/global_norm":
                    total_global_norm += v.simple_value
                elif v.tag in ["loss_1", "loss"]:
                    # SQuAD output stores loss in `loss` key;
                    # classifier stores in `loss_1` key.

                    if e.step == 1:
                        first_loss = v.simple_value
                    cur_loss = v.simple_value

            if checkpoint_step is None or e.step == checkpoint_step:
                ret["steps"][e.step].update({
                    "total_global_norms": total_global_norm,
                    "train_loss": cur_loss,
                    "train_loss_norm": cur_loss / ret["output_dims"]
                })

        ret["first_train_loss"] = first_loss
        ret["first_train_loss_norm"] = first_loss / ret["output_dims"]

    # Load eval events data.
    try:
        eval_events_file = next(savedir.glob("eval/events.*"))
    except StopIteration:
        # no eval events data -- skip
        print("Missing eval events data in savedir:", savedir)
        pass
    else:
        tags = set()
        eval_loss, eval_accuracy = None, None
        for e in tf.train.summary_iterator(str(eval_events_file)):
            for v in e.summary.value:
                tags.add(v.tag)
                if v.tag == "eval_loss":
                    eval_loss = v.simple_value
                elif v.tag == "eval_accuracy":
                    eval_accuracy = v.simple_value
                elif v.tag == "masked_lm_accuracy":
                    eval_accuracy = v.simple_value

            if checkpoint_step is None or e.step == checkpoint_step:
                ret["steps"][e.step].update({
                    "eval_accuracy": eval_accuracy,
                    "eval_loss": eval_loss,
                })

    return ret

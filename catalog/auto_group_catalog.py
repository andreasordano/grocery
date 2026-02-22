#!/usr/bin/env python3
"""Automatically group similar product names into macro-products.

Algorithm (greedy):
- Load `normalized_catalog.json` and extract display names (already normalized).
- Iterate names, matching each against existing cluster representatives using
  SequenceMatcher ratio. If ratio >= threshold -> join cluster, else create new cluster.
- For each cluster, pick a macro label heuristically:
  - If any token in cluster names equals a known macro keyword (e.g., 'riis','kohv'), use that capitalized.
  - Else, choose the most common word across names.
- Write back `normalized_catalog.json` adding `macro` field to records.
- Optionally reload DB (clear and re-insert).

This is lightweight, incremental, and doesn't require external ML libs. It will
handle daily catalog changes automatically by re-running.
"""

import json
import os
import re
import sys
from collections import defaultdict, Counter
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

BASE = os.path.dirname(__file__)
NORM_PATH = os.path.join(BASE, "normalized_catalog.json")
BACKUP = os.path.join(BASE, "normalized_catalog.with_macro.json.bak")

# macro keywords (lowercase) mapped to friendly label
MACRO_KEYWORDS = {
    "riis": "Riis",
    "kohv": "Kohv",
    "juust": "Juust",
    "piim": "Piim",
    "leib": "Leib",
    "sai": "Sai",
    "kana": "Kana",
    "hakkliha": "Hakkliha",
}

THRESHOLD = 0.72


def tfidf_agglomerative_clusters(names, distance_threshold=0.7):
    """Cluster names using TF-IDF + AgglomerativeClustering with cosine distance.

    Returns list of cluster labels aligned with names.
    """
    if not names:
        return []
    # vectorize names (sparse)
    vec = TfidfVectorizer(analyzer="word", token_pattern=r"[\wäöüõšžÄÖÜÕŠŽ]+", ngram_range=(1,2))
    X = vec.fit_transform(names)

    # Dimensionality reduction — essential for speed at scale (e.g., ~6k items)
    n_features = X.shape[1]
    if n_features > 1:
        n_components = min(150, max(1, n_features - 1))
        svd = TruncatedSVD(n_components=n_components, random_state=42)
        X_reduced = svd.fit_transform(X)
        X_reduced = normalize(X_reduced)
    else:
        # Degenerate case: very small vocab, fall back to dense normalization
        X_reduced = normalize(X.toarray())

    # Agglomerative on reduced dense features. distance_threshold is 1 - similarity.
    # Avoid forcing a full tree build — let sklearn decide for performance.
    try:
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - distance_threshold,
            metric="cosine",
            linkage="average",
        )
    except TypeError:
        # older sklearn versions expect `affinity` instead of `metric`
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - distance_threshold,
            affinity="cosine",
            linkage="average",
        )

    labels = model.fit_predict(X_reduced)
    return labels


def load_items(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def words(name):
    tokens = re.findall(r"[\wäöüõšžÄÖÜÕŠŽ]+", name.lower())
    return tokens


def most_common_word(names):
    cnt = Counter()
    for n in names:
        for w in words(n):
            cnt[w] += 1
    if not cnt:
        return None
    return cnt.most_common(1)[0][0]


def build_clusters(names):
    labels = tfidf_agglomerative_clusters(names, distance_threshold=THRESHOLD)
    clusters = defaultdict(list)
    for i, lbl in enumerate(labels):
        clusters[int(lbl)].append(i)
    reps = [names[c[0]] for c in clusters.values()]
    return list(clusters.values()), reps


def pick_macro_for_cluster(names):
    # check keywords
    for n in names:
        for w in words(n):
            if w in MACRO_KEYWORDS:
                return MACRO_KEYWORDS[w]
    # fallback to most common word
    w = most_common_word(names)
    if w:
        return w.capitalize()
    return "Other"


def run_auto_group(norm_path=None, backup=True, reload_db=True, threshold=THRESHOLD):
    path = norm_path or NORM_PATH
    print("Loading", path)
    items = load_items(path)
    names = [rec.get("name", "") for rec in items]
    print("Building clusters for", len(names), "items")
    clusters, reps = build_clusters(names)
    print("Clusters created:", len(clusters))

    # assign macro label per item
    macro_by_index = [None] * len(names)
    for ci, cluster in enumerate(clusters):
        cluster_names = [names[i] for i in cluster]
        macro_label = pick_macro_for_cluster(cluster_names)
        for i in cluster:
            macro_by_index[i] = macro_label

    # attach macro field and write out
    new_items = []
    for i, rec in enumerate(items):
        rec2 = dict(rec)
        rec2["macro"] = macro_by_index[i]
        new_items.append(rec2)

    # backup and save
    if os.path.exists(path) and backup:
        os.replace(path, BACKUP)
        print("Backed up original to", BACKUP)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(new_items, f, ensure_ascii=False, indent=2)
    print("Wrote", len(new_items), "records with macro field to", path)

    if reload_db:
        GROCERIES_DIR = os.path.abspath(os.path.join(BASE, ".."))
        if GROCERIES_DIR not in sys.path:
            sys.path.insert(0, GROCERIES_DIR)
        from core import db
        from core.models import Product

        db.create_tables()
        session = db.SessionLocal()
        try:
            deleted = session.query(Product).delete()
            session.commit()
            print('Cleared products table, deleted rows:', deleted)
        finally:
            session.close()

        inserted = db.load_json_into_db(path)
        print('Inserted into DB:', inserted)


if __name__ == "__main__":
    run_auto_group()

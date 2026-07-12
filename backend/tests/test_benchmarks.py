#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Performance benchmarks for critical paths: semantic search, tokenization,
memory scanning, Jaccard/tf-idf vectorization."""

import os
import tempfile
import time

from encre.memdir.semantic import (
    _build_idf,
    _cosine_similarity,
    _jaccard_similarity,
    _tf_idf_vectorize,
    _tokenize,
)

# ===========================================================================
# Tokenizer benchmarks
# ===========================================================================

class TestTokenizerBench:
    """Test suite for TokenizerBench."""
    def test_tokenize_10k_lines(self):
        """Test: Tokenize 10k lines."""
        text = "Hello world this is a test of the tokenizer. " * 10000
        start = time.perf_counter()
        tokens = _tokenize(text)
        elapsed = time.perf_counter() - start
        # Verify: len(tokens) > 0
        assert len(tokens) > 0
        # Verify: elapsed < 5.0, f"tokenize 10k lines took {elapsed:.2f}s"
        assert elapsed < 5.0, f"tokenize 10k lines took {elapsed:.2f}s"

    def test_tokenize_chinese(self):
        """Test: Tokenize chinese."""
        text = "测试中文分词效果 这是一个测试 " * 5000
        start = time.perf_counter()
        _tokenize(text)
        elapsed = time.perf_counter() - start
        # Verify: elapsed < 5.0, f"tokenize Chinese took {elapsed:.2f}s"
        assert elapsed < 5.0, f"tokenize Chinese took {elapsed:.2f}s"


# ===========================================================================
# Jaccard benchmarks
# ===========================================================================

class TestJaccardBench:
    """Test suite for JaccardBench."""
    def test_jaccard_1000_pairs(self):
        """Test: Jaccard 1000 pairs."""
        docs = [f"This is document number {i} about various topics including python, rust, typescript, and more." for i in range(100)]  # noqa: E501
        start = time.perf_counter()
        for i in range(len(docs) - 1):
            _jaccard_similarity(docs[i], docs[i + 1])
        elapsed = time.perf_counter() - start
        # Verify: elapsed < 1.0, f"1000 Jaccard pairs took {elapsed:.2f}s"
        assert elapsed < 1.0, f"1000 Jaccard pairs took {elapsed:.2f}s"

    def test_jaccard_empty(self):
        """Test: Jaccard empty."""
        start = time.perf_counter()
        for _ in range(10000):
            _jaccard_similarity("", "")
        elapsed = time.perf_counter() - start
        # Verify: elapsed < 0.5, f"10000 empty Jaccard took {elapsed:.2f}s"
        assert elapsed < 0.5, f"10000 empty Jaccard took {elapsed:.2f}s"


# ===========================================================================
# TF-IDF benchmarks
# ===========================================================================

class TestTfIdfBench:
    """Test suite for TfIdfBench."""
    def test_build_idf_large_corpus(self):
        """Test: Build idf large corpus."""
        corpus = [f"Document {i}: contains words about various topics like python programming and async rust development." for i in range(1000)]  # noqa: E501
        start = time.perf_counter()
        idf = _build_idf(corpus)
        elapsed = time.perf_counter() - start
        # Verify: len(idf) > 0
        assert len(idf) > 0
        # Verify: elapsed < 2.0, f"build_idf 1000 docs took {elapsed:.2f}s"
        assert elapsed < 2.0, f"build_idf 1000 docs took {elapsed:.2f}s"

    def test_vectorize_and_cosine(self):
        """Test: Vectorize and cosine."""
        corpus = [f"Document {i}: python rust typescript async programming patterns" for i in range(500)]  # noqa: E501
        idf = _build_idf(corpus)
        vocab = set(idf.keys())
        vecs = [_tf_idf_vectorize(doc, idf, vocab) for doc in corpus]
        start = time.perf_counter()
        for i in range(len(vecs) - 1):
            _cosine_similarity(vecs[i], vecs[i + 1])
        elapsed = time.perf_counter() - start
        # Verify: elapsed < 1.0, f"500 cosine pairs took {elapsed:.2f}s"
        assert elapsed < 1.0, f"500 cosine pairs took {elapsed:.2f}s"


# ===========================================================================
# Memory scan benchmarks
# ===========================================================================

class TestMemoryScanBench:
    """Test suite for MemoryScanBench."""
    def test_scan_large_memory_dir(self):
        """Test: Scan large memory dir."""
        tmpdir = tempfile.mkdtemp()
        # Create 200 memory files
        for i in range(200):
            with open(os.path.join(tmpdir, f"memory_{i:04d}.md"), "w", encoding="utf-8") as f:
                f.write(f"---\ndescription: Memory {i}\ntype: reference\n---\n\nContent for memory {i}.\n" * 10)  # noqa: E501

        from encre.memdir.system import EncreMemorySystem
        ms = EncreMemorySystem(tmpdir)
        start = time.perf_counter()
        memories = ms.scan()
        elapsed = time.perf_counter() - start
        # Verify: len(memories) > 0
        assert len(memories) > 0
        # Verify: elapsed < 3.0, f"scan 200 files took {elapsed:.2f}s"
        assert elapsed < 3.0, f"scan 200 files took {elapsed:.2f}s"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_semantic_search_performance(self):
        """Test: Semantic search performance."""
        tmpdir = tempfile.mkdtemp()
        for i in range(100):
            with open(os.path.join(tmpdir, f"doc_{i:04d}.md"), "w", encoding="utf-8") as f:
                f.write(f"Document {i} about python programming and async patterns.\n" * 5)

        from encre.memdir.semantic import SemanticMemorySearch
        sms = SemanticMemorySearch(tmpdir)
        start = time.perf_counter()
        results = sms.search("python async programming", top_k=10)
        elapsed = time.perf_counter() - start
        # Verify: len(results) > 0
        assert len(results) > 0
        # Verify: elapsed < 2.0, f"semantic search 100 docs took {elapsed:.2f}s"
        assert elapsed < 2.0, f"semantic search 100 docs took {elapsed:.2f}s"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ===========================================================================
# Consolidation benchmarks
# ===========================================================================

class TestConsolidationBench:
    """Test suite for ConsolidationBench."""
    def test_consolidate_many_files(self):
        """Test: Consolidate many files."""
        tmpdir = tempfile.mkdtemp()
        from encre.memdir.semantic import MemoryConsolidator

        files = {}
        for i in range(50):
            files[f"doc_{i:04d}.md"] = f"Document {i} about {'async programming' if i % 2 == 0 else 'CSS styling'} patterns and best practices.\n" * 3  # noqa: E501

        mc = MemoryConsolidator(tmpdir)
        start = time.perf_counter()
        mc.consolidate(files, {})
        elapsed = time.perf_counter() - start
        # Verify: elapsed < 2.0, f"consolidate 50 files took {elapsed:.2f}s"
        assert elapsed < 2.0, f"consolidate 50 files took {elapsed:.2f}s"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

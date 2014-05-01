#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import math
import re
from collections import Counter

class Corpus_ComputeStats():
	
	DEFAULT_STOPWORDS = 'tools/mallet/stoplists/en.txt'
	
	def __init__(self, corpus_db, corpusFilename, sentencesFilename, STOPWORDS = None):
		self.logger = logging.getLogger('termite')
		self.corpus_db = corpus_db
		self.db = self.corpus_db.db
		self.corpusFilename = corpusFilename
		self.sentencesFilename = sentencesFilename
		
		self.tokenRegexStr = corpus_db.GetOption('token_regex')
		self.tokenRegex = re.compile(self.tokenRegexStr)
		self.minFreq = int(self.corpus_db.GetOption('min_freq'))
		self.minDocFreq = int(self.corpus_db.GetOption('min_doc_freq'))
		self.maxFreqCount = int(self.corpus_db.GetOption('max_freq_count'))
		self.maxCoFreqCount = int(self.corpus_db.GetOption('max_co_freq_count'))
		self.maxG2Count = int(self.corpus_db.GetOption('max_g2_count'))
		self.maxPMICount = int(self.corpus_db.GetOption('max_pmi_count'))
		self.stopwords = self.LoadStopwords(STOPWORDS if STOPWORDS is not None else Corpus_ComputeStats.DEFAULT_STOPWORDS)
	
	def Execute(self):
		self.logger.info( 'Corpus statistics' )
		self.logger.info( '          token_regex = %s', self.tokenRegexStr )
		self.logger.info( '             min_freq = %d', self.minFreq )
		self.logger.info( '         min_doc_freq = %d', self.minDocFreq )
		self.logger.info( '       max_freq_count = %d', self.maxFreqCount )
		self.logger.info( '    max_co_freq_count = %d', self.maxCoFreqCount )
		self.logger.info( '         max_g2_count = %d', self.maxG2Count )
		self.logger.info( '        max_pmi_count = %d', self.maxPMICount )
		self.logger.info( 'Computing document-level statistics...' )
		self.ComputeAndSaveDocumentLevelStatistics()
		self.logger.info( 'Computing sentence-level term statistics...' )
		self.ComputeAndSaveSentenceLevelStatistics()
		self.corpus_db.AddModel('corpus', 'Text corpus')
			
	def LoadStopwords(self, filename):
		stopwords = []
		with open( filename, 'r' ) as f:
			stopwords = f.read().decode('utf-8', 'ignore').splitlines()
		return frozenset(stopwords)
	
	def ReadCorpus(self, filename):
		self.logger.debug( '    Loading corpus: %s', filename )
		with open( filename, 'r' ) as f:
			for line in f:
				docID, docContent = line.decode('utf-8').rstrip('\n').split('\t')
				docTokens = self.tokenRegex.findall(docContent)
				docTokens = [ token.lower() for token in docTokens if token not in self.stopwords ]
				yield docID, docTokens
	
	def UnfoldVocab(self):
		data = []
		for term, index in self.termLookup.iteritems():
			data.append({ 'term_index' : index, 'term_text' : term })
		return data
	
	def UnfoldStats(self, stats):
		data = []
		for term, index in self.termLookup.iteritems():
			if term in stats:
				data.append({ 'term_index' : index, 'value' : stats[term], 'rank' : 0 })
		data.sort( key = lambda x : -x['value'] )
		for rank, d in enumerate(data):
			d['rank'] = rank+1
		return data
	
	def UnfoldCoStats(self, coStats):
		data = []
		for first_term, stats in coStats.iteritems():
			first_term_index = self.termLookup[first_term]
			for second_term, value in stats.iteritems():
				second_term_index = self.termLookup[second_term]
				data.append({ 'first_term_index' : first_term_index, 'second_term_index' : second_term_index, 'value' : value, 'rank' : 0 })
		data.sort( key = lambda x : -x['value'] )
		for rank, d in enumerate(data):
			d['rank'] = rank+1
		return data
	
	def ComputeAndSaveDocumentLevelStatistics(self):
		reader = self.ReadCorpus( self.corpusFilename )
		corpus = { docID : docTokens for docID, docTokens in reader }
		termStats = self.ComputeTermFreqs( corpus )
		self.ComputeVocabulary( termStats )
		termCoStats = self.ComputeTermCoFreqs( corpus, termStats )
		
		self.logger.debug( '    Saving term_texts (%d terms)...', len(self.vocab) )
		rows = self.UnfoldVocab()
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_texts.bulk_insert(rows)
		self.logger.debug( '    Saving term_freqs (%d terms)...', len(self.vocab) )
		rows = self.UnfoldStats(termStats['term_freqs'])
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_freqs.bulk_insert(rows)
		self.logger.debug( '    Saving term_probs (%d terms)...', len(self.vocab) )
		rows = self.UnfoldStats(termStats['term_probs'])
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_probs.bulk_insert(rows)
		self.logger.debug( '    Saving term_doc_freqs (%d terms)...', len(self.vocab) )
		rows = self.UnfoldStats(termStats['term_doc_freqs'])
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_doc_freqs.bulk_insert(rows)
		
		coStats = termCoStats['co_freqs']
		self.logger.debug( '    Saving term_co_freqs (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxCoFreqCount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxCoFreqCount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_co_freqs.bulk_insert(rows)
		coStats = termCoStats['co_probs']
		self.logger.debug( '    Saving term_co_probs (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxCoFreqCount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxCoFreqCount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_co_probs.bulk_insert(rows)
		coStats = termCoStats['g2']
		self.logger.debug( '    Saving term_g2 (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxG2Count) )
		rows = self.UnfoldCoStats(coStats)[:self.maxG2Count]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_g2.bulk_insert(rows)
		coStats = termCoStats['pmi']
		self.logger.debug( '    Saving term_pmi (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxPMICount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxPMICount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.term_pmi.bulk_insert(rows)
	
	def ComputeAndSaveSentenceLevelStatistics(self):
		reader = self.ReadCorpus( self.sentencesFilename )
		corpus = { docID : docTokens for docID, docTokens in reader }
		termStats = self.ComputeTermFreqs( corpus )
		termCoStats = self.ComputeTermCoFreqs( corpus, termStats )

		coStats = termCoStats['co_freqs']
		self.logger.debug( '    Saving sentences_co_freqs (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxCoFreqCount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxCoFreqCount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.sentences_co_freqs.bulk_insert(rows)
		coStats = termCoStats['co_probs']
		self.logger.debug( '    Saving sentences_co_probs (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxCoFreqCount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxCoFreqCount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.sentences_co_probs.bulk_insert(rows)
		coStats = termCoStats['g2']
		self.logger.debug( '    Saving sentences_g2 (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxG2Count) )
		rows = self.UnfoldCoStats(coStats)[:self.maxG2Count]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.sentences_g2.bulk_insert(rows)
		coStats = termCoStats['pmi']
		self.logger.debug( '    Saving sentences_pmi (%d term pairs)...', min(sum(len(stats) for stats in coStats.itervalues()), self.maxPMICount) )
		rows = self.UnfoldCoStats(coStats)[:self.maxPMICount]
		self.logger.debug( '        inserting %d rows...', len(rows) )
		self.db.sentences_pmi.bulk_insert(rows)
	
	def ComputeTermFreqs(self, corpus):
		def ComputeFreqs(corpus):
			freqs = Counter()
			for docID, docTokens in corpus.iteritems():
				freqs.update( docTokens )
			return freqs
		
		def ComputeDocFreqs(corpus):
			docFreqs = Counter()
			for docID, docTokens in corpus.iteritems():
				uniqueTokens = frozenset( docTokens )
				docFreqs.update( uniqueTokens )
			return docFreqs
		
		def NormalizeFreqs(freqs):
			normalization = sum( freqs.itervalues() )
			normalization = 1.0 / normalization if normalization > 1.0 else 1.0
			probs = { term : freq * normalization for term, freq in freqs.iteritems() }
			return probs
		
		def ComputeIdfs(corpus, docFreqs):
			N = len( corpus )
			idfs = { term : math.log( 1.0 * N / docFreq ) for term, docFreq in docFreqs.iteritems() }
			return idfs
		
		def ComputeTfIdfs( freqs, idfs ):
			tfIdfs = { term : freq * idfs[term] for term, freq in freqs.iteritems() }
			return tfIdfs
		
		self.logger.info( '    Computing term freqs (%d docs)...', len(corpus) )
		termFreqs = ComputeFreqs( corpus )
		termDocFreqs = ComputeDocFreqs( corpus )
		termProbs = NormalizeFreqs( termFreqs )
		termStats = {
			'term_freqs' : termFreqs,
			'term_probs' : termProbs,
			'term_doc_freqs' : termDocFreqs
		}
		return termStats
	
	def ComputeVocabulary(self, termStats):
		minFreq = self.minFreq
		minDocFreq = self.minDocFreq
		maxFreqCount = self.maxFreqCount
		termFreqs = termStats['term_freqs']
		termDocFreqs = termStats['term_doc_freqs']
		keys = [ term for term in termFreqs if termFreqs[term] >= minFreq and termDocFreqs[term] >= minDocFreq ]
		keys = sorted( keys, key = lambda x : -termFreqs[x] )
		keys = keys[:maxFreqCount]
		self.vocab = frozenset(keys)
		self.termLookup = { key : index for index, key in enumerate(keys) }
		
	def ComputeTermCoFreqs(self, corpus, termStats):
		termProbs = termStats['term_probs']
		
		def GetTokenPairs(firstToken, secondToken):
			if firstToken < secondToken:
				return firstToken, secondToken
			else:
				return secondToken, firstToken
		
		def ComputeJointFreqs(corpus, vocab):
			jointFreqs = {}
			allFreq = 0
			allCoFreq = 0
			for docID, docTokens in corpus.iteritems():
				freqs = Counter( docTokens )
				allFreq += sum( freqs.itervalues() )
				for firstToken, firstFreq in freqs.iteritems():
					for secondToken, secondFreq in freqs.iteritems():
						coFreq = firstFreq * secondFreq
						allCoFreq += coFreq
						if firstToken in vocab and secondToken in vocab and firstToken < secondToken:
							if firstToken not in jointFreqs:
								jointFreqs[firstToken] = { secondToken : coFreq }
							elif secondToken not in jointFreqs[firstToken]:
								jointFreqs[firstToken][secondToken] = coFreq
							else:
								jointFreqs[firstToken][secondToken] += coFreq
			return jointFreqs, allFreq, allCoFreq
		
		def NormalizeJointFreqs(jointFreqs, normalization=None):
			if normalization is None:
				normalization = sum( sum( d.itervalues() ) for d in jointFreqs.itervalues() )
				normalization = 1.0 / normalization if normalization > 1.0 else 1.0
			jointProbs = { term : { t : f * normalization for t, f in freqs.iteritems() } for term, freqs in jointFreqs.iteritems() }
			return jointProbs
		
		def ComputePMI(marginalProbs, jointProbs):
			pmi = {}
			for firstToken, d in jointProbs.iteritems():
				if firstToken in marginalProbs:
					firstDenominator = 1.0 / marginalProbs[firstToken] if marginalProbs[firstToken] > 0.0 else 0.0
					pmi[ firstToken ] = {}
					for secondToken, prob in d.iteritems():
						if secondToken in marginalProbs:
							secondDenominator = 1.0 / marginalProbs[secondToken] if marginalProbs[secondToken] > 0.0 else 0.0
							pmi[ firstToken ][ secondToken ] = prob * firstDenominator * secondDenominator
#							if firstToken == 'data' or secondToken == 'data':
#								print '{} + {} :: {} * {} * {} --> {}'.format( firstToken, secondToken, prob, firstDenominator, secondDenominator, pmi[ firstToken ][ secondToken ] )
			return pmi
		
		def GetBinomial(B_given_A, any_given_A, B_given_notA, any_given_notA):
			assert B_given_A >= 0
			assert B_given_notA >= 0
			assert any_given_A >= B_given_A
			assert any_given_notA >= B_given_notA
			
			a = float( B_given_A )
			b = float( B_given_notA )
			c = float( any_given_A )
			d = float( any_given_notA )
			E1 = c * ( a + b ) / ( c + d )
			E2 = d * ( a + b ) / ( c + d )
			g2a = a * math.log( a / E1 ) if a > 0 else 0
			g2b = b * math.log( b / E2 ) if b > 0 else 0
			return 2 * ( g2a + g2b )
		
		def GetG2Stats(freq_all, freq_ab, freq_a, freq_b, a, b):
#			assert freq_all >= freq_a
#			assert freq_all >= freq_b
#			assert freq_a >= freq_ab
#			assert freq_b >= freq_ab
#			assert freq_all >= 0
#			assert freq_ab >= 0
#			assert freq_a >= 0
#			assert freq_b >= 0
			if not (freq_ab >= 0):
				freq_ab = 0
				self.logger.warning('assertion failed: freq(%s, %s) >= 0', a, b)
			if not (freq_a >= freq_ab):
				freq_a = freq_ab
				self.logger.warning('assertion failed: freq(%s) >= freq(%s, %s)', a, a, b)
			if not (freq_b >= freq_ab):
				freq_b = freq_ab
				self.logger.warning('assertion failed: freq(%s) >= freq(%s, %s)', b, a, b)
			if not (freq_all >= freq_a and freq_all >= freq_b):
				freq_all = max(freq_a, freq_b)
				self.logger.warning('assertion failed: freq >= freq(%s) and freq >= freq(%s)', a, b)
			
			B_given_A = freq_ab
			B_given_notA = freq_b - freq_ab
			any_given_A = freq_a
			any_given_notA = freq_all - freq_a
			return GetBinomial( B_given_A, any_given_A, B_given_notA, any_given_notA )
		
		def ComputeG2Stats(allFreq, marginalProbs, jointProbs):
			g2_stats = {}
			freq_all = allFreq
			for firstToken, d in jointProbs.iteritems():
				if firstToken in marginalProbs:
					freq_a = allFreq * marginalProbs[ firstToken ]
					g2_stats[ firstToken ] = {}
					for secondToken, jointProb in d.iteritems():
						if secondToken in marginalProbs:
							freq_b = allFreq * marginalProbs[ secondToken ]
							freq_ab = allFreq * jointProb
							g2_stats[ firstToken ][ secondToken ] = GetG2Stats( freq_all, freq_ab, freq_a, freq_b, firstToken, secondToken )
			return g2_stats
		
		self.logger.info( '    Computing term co-occurrences (%d docs)...', len(corpus) )
		
		# Count co-occurrences
		termCoFreqs, allFreq, allCoFreq = ComputeJointFreqs( corpus, self.vocab )
		
		# Normalize to create joint probability distribution
		termCoProbs = NormalizeJointFreqs( termCoFreqs, 1.0 / allCoFreq if allCoFreq > 1.0 else 1.0 )
		
		# Compute pointwise mutual information from marginal/joint probability distributions
		termPMI = ComputePMI( termProbs, termCoProbs )
		
		# Compute G2 statistics
		termG2 = ComputeG2Stats( allFreq, termProbs, termCoProbs )
		
		termCoStats = {
			'co_freqs' : termCoFreqs,
			'co_probs' : termCoProbs,
			'pmi' : termPMI,
			'g2' : termG2
		}
		return termCoStats

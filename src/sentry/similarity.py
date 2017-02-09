from __future__ import absolute_import

import itertools
import logging
import math
import operator
import struct

import mmh3

from sentry.utils.iterators import shingle


def scale_to_total(value):
    """\
    Convert a mapping of distinct quantities to a mapping of proportions of the
    total quantity.
    """
    total = float(sum(value.values()))
    return {k: (v / total) for k, v in value.items()}


def get_euclidian_distance(target, other):
    """\
    Calculate the N-dimensional Euclidian between two mappings.

    The mappings are used to represent sparse arrays -- if a key is not present
    in both mappings, it's assumed to be 0 in the mapping where it is missing.
    """
    return math.sqrt(
        sum(
            (target.get(k, 0) - other.get(k, 0)) ** 2
            for k in set(target) | set(other)
        )
    )


def get_manhattan_distance(target, other):
    """\
    Calculate the N-dimensional Manhattan distance between two mappings.

    The mappings are used to represent sparse arrays -- if a key is not present
    in both mappings, it's assumed to be 0 in the mapping where it is missing.

    The result of this function will be expressed as the distance between the
    caller and a 5:2 ratio of rye whiskey to sweet Italian vermouth, with a
    dash of bitters.
    """
    return sum(
        abs(target.get(k, 0) - other.get(k, 0))
        for k in set(target) | set(other)
    )


formats = sorted([
    (2 ** 8 - 1, 'B'),
    (2 ** 16 - 1, 'H'),
    (2 ** 32 - 1, 'L'),
    (2 ** 64 - 1, 'Q'),
])


def get_number_format(size, width=1):
    """\
    Returns a ``Struct`` object that can be used packs (and unpack) a number no
    larger than the provided size into to an efficient binary representation.
    """
    assert size > 0

    for maximum, format in formats:
        if maximum >= size:
            return struct.Struct('>%s' % (format * width))

    raise ValueError('No registered formatter can handle the provided value.')


class MinHashIndex(object):
    """\
    Implements an index that can be used to efficiently search for items that
    share similar characteristics.

    This implementation is based on MinHash (which is used quickly identify
    similar items and estimate the Jaccard similarity of their characteristic
    sets) but this implementation extends the typical design to add the ability
    to record items by an arbitrary key. This allows querying for similar
    groups that contain many different characteristic sets.

    The ``rows`` parameter is the size of the hash ring used to collapse the
    domain of all tokens to a fixed-size range. The total size of the LSH
    signature is ``bands * buckets``. These attributes control the distribution
    of data within the index, and modifying them after data has already been
    written will cause data loss and/or corruption.

    This is modeled as two data structures:

    - A bucket frequency sorted set, which maintains a count of what buckets
      have been recorded -- and how often -- in a ``(band, key)`` pair. This
      data can be used to identify what buckets a key is a member of, and also
      used to identify the degree of bucket similarity when comparing with data
      associated with another key.
    - A bucket membership set, which maintains a record of what keys have been
      record in a ``(band, bucket)`` pair. This data can be used to identify
      what other keys may be similar to the lookup key (but not the degree of
      similarity.)
    """
    BUCKET_MEMBERSHIP = '0'
    BUCKET_FREQUENCY = '1'

    def __init__(self, cluster, rows, bands, buckets):
        self.namespace = b'sim'

        self.cluster = cluster
        self.rows = rows

        sequence = itertools.count()
        self.bands = [[next(sequence) for j in xrange(buckets)] for i in xrange(bands)]

        self.__bucket_format = get_number_format(rows, buckets)

    def get_signature(self, value):
        """Generate a signature for a value."""
        return map(
            lambda band: map(
                lambda bucket: min(
                    map(
                        lambda item: mmh3.hash(item, bucket) % self.rows,
                        value,
                    ),
                ),
                band,
            ),
            self.bands,
        )

    def get_similarity(self, target, other):
        """\
        Calculate the degree of similarity between two bucket frequency
        sequences which represent two different keys.

        This is mainly an implementation detail for sorting query results, but
        is exposed publically for testing. This method assumes all input
        values have already been normalized using ``scale_to_total``.
        """
        assert len(target) == len(other)
        assert len(target) == len(self.bands)
        return sum(
            map(
                lambda (left, right): 1 - (
                    get_manhattan_distance(
                        left,
                        right,
                    ) / 2.0
                ),
                zip(target, other)
            )
        ) / len(target)

    def query(self, scope, key):
        """\
        Find other entries that are similar to the one repesented by ``key``.

        This returns an sequence of ``(key, estimated similarity)`` pairs,
        where a similarity score of 1 is completely similar, and a similarity
        score of 0 is completely dissimilar. The result sequence is ordered
        from most similar to least similar. (For example, the search key itself
        isn't filtered from the result and will always have a similarity of 1,
        typically making it the first result.)
        """
        def fetch_bucket_frequencies(keys):
            """Fetch the bucket frequencies for each band for each provided key."""
            with self.cluster.map() as client:
                responses = {
                    key: map(
                        lambda band: client.zrange(
                            b'{}:{}:{}:{}:{}'.format(self.namespace, scope, self.BUCKET_FREQUENCY, band, key),
                            0,
                            -1,
                            desc=True,
                            withscores=True,
                        ),
                        range(len(self.bands)),
                    ) for key in keys
                }

            result = {}
            for key, promises in responses.items():
                # Resolve each promise, and scale the number of observations
                # for each bucket to [0,1] value (the proportion of items
                # observed in that band that belong to the bucket for the key.)
                result[key] = map(
                    lambda promise: scale_to_total({
                        self.__bucket_format.unpack(k): v for k, v in promise.value
                    }),
                    promises,
                )

            return result

        def fetch_candidates(signature):
            """Fetch all the similar candidates for a given signature."""
            with self.cluster.map() as client:
                responses = map(
                    lambda (band, buckets): map(
                        lambda bucket: client.smembers(
                            b'{}:{}:{}:{}:{}'.format(
                                self.namespace,
                                scope,
                                self.BUCKET_MEMBERSHIP,
                                band,
                                self.__bucket_format.pack(*bucket),
                            )
                        ),
                        buckets,
                    ),
                    enumerate(signature),
                )

            # Resolve all of the promises for each band and reduce them into a
            # single set per band.
            return map(
                lambda band: reduce(
                    lambda values, promise: values | promise.value,
                    band,
                    set(),
                ),
                responses,
            )

        target_frequencies = fetch_bucket_frequencies([key])[key]

        # Flatten the results of each band into a single set. (In the future we
        # might want to change this to only calculate the similarity for keys
        # that show up in some threshold number of bands.)
        candidates = reduce(
            lambda total, band: total | band,
            fetch_candidates(target_frequencies),
            set(),
        )

        return sorted(
            map(
                lambda (key, candidate_frequencies): (
                    key,
                    self.get_similarity(
                        target_frequencies,
                        candidate_frequencies,
                    ),
                ),
                fetch_bucket_frequencies(candidates).items(),
            ),
            key=lambda (key, similarity): (similarity * -1, key),
        )

    def record_multi(self, items):
        """\
        Records the presence of a set of characteristics within a group for a
        batch of items. Each item should be represented by a 3-tuple of
        ``(scope, key, characteristics)``.
        """
        with self.cluster.map() as client:
            for scope, key, characteristics in items:
                for band, buckets in enumerate(self.get_signature(characteristics)):
                    buckets = self.__bucket_format.pack(*buckets)
                    client.sadd(
                        b'{}:{}:{}:{}:{}'.format(self.namespace, scope, self.BUCKET_MEMBERSHIP, band, buckets),
                        key,
                    )
                    client.zincrby(
                        b'{}:{}:{}:{}:{}'.format(self.namespace, scope, self.BUCKET_FREQUENCY, band, key),
                        buckets,
                        1,
                    )

    def record(self, scope, key, characteristics):
        """Records the presence of a set of characteristics within a group."""
        return self.record_multi([
            (scope, key, characteristics),
        ])


FRAME_ITEM_SEPARATOR = b'\x00'
FRAME_PAIR_SEPARATOR = b'\x01'
FRAME_SEPARATOR = b'\x02'

FRAME_FUNCTION_KEY = b'\x10'
FRAME_MODULE_KEY = b'\x12'
FRAME_FILENAME_KEY = b'\x13'


def serialize_frame(frame):
    # TODO(tkaemming): This should likely result in an intermediate data
    # structure that is easier to introspect than this one, and a separate
    # serialization step before hashing.
    # TODO(tkaemming): These frame values need platform-specific normalization.
    # This probably should be done prior to this method being called...?
    attributes = {
        FRAME_FUNCTION_KEY: frame['function']
    }

    module = frame.get('module')
    if module:
        attributes[FRAME_MODULE_KEY] = module
    else:
        attributes[FRAME_FILENAME_KEY] = frame['filename']

    return FRAME_ITEM_SEPARATOR.join(
        map(
            lambda item: FRAME_PAIR_SEPARATOR.join(
                map(
                    operator.methodcaller('encode', 'utf8'),
                    item,
                ),
            ),
            attributes.items(),
        ),
    )


def get_application_chunks(exception):
    return map(
        lambda (in_app, frames): list(frames),
        itertools.ifilter(
            lambda (in_app, frames): in_app,
            itertools.groupby(
                exception['stacktrace']['frames'],
                key=lambda frame: frame.get('in_app', False),
            )
        )
    )


class ExceptionProcessor(object):
    def __init__(self, function):
        self.function = function
        self.logger = logging.getLogger(__name__)

    def process(self, event):
        try:
            exceptions = event.data['sentry.interfaces.Exception']['values']
        except KeyError as error:
            self.logger.info('Could not create signature(s) for %r due error: %r', event, error, exc_info=True)
            return

        for exception in exceptions:
            try:
                # TODO: This shouldn't change the return type of the wrapped function (that can hide errors.)
                yield set(self.function(exception))
            except Exception as error:
                self.logger.exception('Could not create signature for exception in %r due to error: %r', event, error)


class MessageProcessor(object):
    def __init__(self, function):
        self.function = function
        self.logger = logging.getLogger(__name__)

    def process(self, event):
        try:
            message = event.data['sentry.interfaces.Message']
        except KeyError as error:
            self.logger.info('Could not create signature(s) for %r due error: %r', event, error, exc_info=True)
            return

        try:
            # TODO: This shouldn't change the return type of the wrapped function (that can hide errors.)
            yield set(self.function(message))
        except Exception as error:
            self.logger.exception('Could not create signature for message of %r due to error: %r', event, error)


processors = {
    'exception:message:character-shingles': ExceptionProcessor(
        lambda exception: map(
            ''.join,
            shingle(
                13,
                exception['value'].encode('utf8'),  # TODO: This should probably happen *after* shingling?
            ),
        )
    ),
    'exception:stacktrace:application-chunks': ExceptionProcessor(
        lambda exception: map(
            lambda frames: FRAME_SEPARATOR.join(
                map(
                    serialize_frame,
                    frames,
                ),
            ),
            get_application_chunks(exception),
        ),
    ),
    'exception:stacktrace:pairs': ExceptionProcessor(
        lambda exception: map(
            FRAME_SEPARATOR.join,
            shingle(
                2,
                map(
                    serialize_frame,
                    exception['stacktrace']['frames'],
                ),
            ),
        ),
    ),
    'message:message:character-shingles': MessageProcessor(
        lambda message: map(
            ''.join,
            shingle(
                13,
                message['message'].encode('utf8'),  # TODO: This should probably happen *after* singling?
            ),
        ),
    ),
}

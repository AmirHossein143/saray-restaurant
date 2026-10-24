"""Static files storage for production."""

import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class LenientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed, compressed static files that never turn a missing file into a 500.

    With the default storage, a template referencing a static file that was
    not collected (for example a photo added after the last ``collectstatic``)
    raises ``ValueError`` and every page using it fails. Here the unhashed URL
    is returned instead, so at worst one image 404s, and a warning is logged.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            logger.warning('Static file %r is missing; run collectstatic.', name)
            return name

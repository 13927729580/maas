# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Celery settings for the region controller.

Do not edit this file.  Instead, put custom settings in a module named
maas_local_celeryconfig.py somewhere on the PYTHONPATH.
"""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
)

str = None

__metaclass__ = type

from datetime import timedelta

import celeryconfig_common
from maas import import_settings

# Region worker queue.  Will be overridden by the customized setting in the
# local MAAS Celery config.
WORKER_QUEUE_REGION = None
CELERY_IMPORTS = None

import_settings(celeryconfig_common)

CELERY_IMPORTS = CELERY_IMPORTS + (
    # Master tasks.
    "maasserver.tasks",
)

try:
    import maas_local_celeryconfig
except ImportError:
    pass
else:
    import_settings(maas_local_celeryconfig)

CLEANUP_OLD_NONCES_SCHEDULE = timedelta(days=1)
IMPORT_BOOT_IMAGES_SCHEDULE = timedelta(days=7)

CELERYBEAT_SCHEDULE = {
    'cleanup-old-nonces': {
        'task': 'maasserver.tasks.cleanup_old_nonces',
        'schedule': CLEANUP_OLD_NONCES_SCHEDULE,
        'options': {
            'queue': WORKER_QUEUE_REGION,
            'expires': int(CLEANUP_OLD_NONCES_SCHEDULE.total_seconds()),
        },
    },

    # Periodically (re-)import boot images.  This is a job for the region
    # controller, although the region controller delegates it to the clusters.
    'import-boot-images': {
        'task': 'maasserver.tasks.import_boot_images_on_schedule',
        'schedule': IMPORT_BOOT_IMAGES_SCHEDULE,
        'options': {
            'queue': WORKER_QUEUE_REGION,
            'expires': int(IMPORT_BOOT_IMAGES_SCHEDULE.total_seconds()),
        },
    },
}

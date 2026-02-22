from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models

class ReviewItem(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("APPROVED", "Approved"),
        ("RETURNED", "Returned"),
    ]
    orphan_id = models.BigIntegerField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="submitted_items")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="reviewed_items")
    reviewer_comment = models.TextField(null=True, blank=True)
    updated_utc = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Orphan {self.orphan_id} - {self.status}"
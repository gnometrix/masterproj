
# Create your models here.
from django.db import models

class Feedback(models.Model):
    name = models.CharField(max_length=255)  # To store the name
    email = models.EmailField()  # To store the email address
    rating = models.IntegerField()  # To store the star rating (1-5)
    feedback_text = models.TextField(blank=True, null=True)  # Optional feedback text
    submitted_at = models.DateTimeField(auto_now_add=True)  # Timestamp of submission

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.rating} Stars"

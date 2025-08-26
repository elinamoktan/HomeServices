# utils/ratings.py
from django.db.models import Avg

def bayesian_average(worker, rating_model, m=5):
    """
    Calculates Bayesian average rating for a worker.

    Parameters:
    - worker: the Worker instance
    - rating_model: the model containing ratings (WorkerRating)
    - m: smoothing constant (default is 5)

    Returns:
    - Bayesian average rating (float)
    """

    # C = overall average rating across all workers
    C = rating_model.objects.aggregate(Avg('rating'))['rating__avg'] or 0

    # R = average rating for this specific worker
    ratings = rating_model.objects.filter(worker=worker)
    n = ratings.count()
    R = ratings.aggregate(Avg('rating'))['rating__avg'] or 0

    # Apply the Bayesian average formula
    return round((n / (n + m)) * R + (m / (n + m)) * C, 2)

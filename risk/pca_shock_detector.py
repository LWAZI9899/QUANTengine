import numpy as np

class PCASystemicShockDetector:
    """Uses Principal Component Analysis (PCA) on return matrices to detect macro systemic shocks

    by monitoring the variance explained by the first principal component (PC1).
    """
    def __init__(self, threshold_ratio: float = 0.82):
        self.threshold_ratio = threshold_ratio  # If PC1 explains > 82% variance, systemic shock is active

    def evaluate_systemic_shock(self, returns_matrix: np.ndarray) -> tuple[bool, float]:
        """Computes eigendecomposition of the return correlation matrix and returns shock status + PC1 ratio."""
        T, N = returns_matrix.shape
        if T <= N or N <= 1:
            return False, 0.0

        # 1. Standardize returns
        std_devs = np.std(returns_matrix, axis=0)
        std_devs = np.where(std_devs < 1e-12, 1e-12, std_devs)
        norm_returns = (returns_matrix - np.mean(returns_matrix, axis=0)) / std_devs

        # 2. Correlation matrix and eigendecomposition
        corr_matrix = np.corrcoef(norm_returns, rowvar=False)
        if np.isnan(corr_matrix).any():
            return False, 0.0

        eigenvalues, _ = np.linalg.eigh(corr_matrix)
        
        # Sort eigenvalues descending
        eigenvalues = np.sort(eigenvalues)[::-1]
        total_variance = np.sum(eigenvalues)

        if total_variance <= 0:
            return False, 0.0

        # 3. Compute variance explained by the first principal component (PC1)
        pc1_ratio = float(eigenvalues[0] / total_variance)

        is_shock = pc1_ratio >= self.threshold_ratio
        return is_shock, pc1_ratio
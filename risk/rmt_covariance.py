import numpy as np


class MarchenkoPasturCovarianceDenoiser:
    """Denoises empirical covariance matrices using Random Matrix Theory (RMT)

    by cleaning noise eigenvalues via the Marchenko-Pastur theorem on correlation space.
    """

    def __init__(self, q_ratio: float = 0.2):
        # q_ratio = N / T (number of variables N divided by sample length T)
        self.q_ratio = q_ratio

    def denoise_covariance(self, returns_matrix: np.ndarray) -> np.ndarray:
        """Takes an (T x N) returns matrix, computes correlation, filters random noise

        eigenvalues, and reconstructs a stable denoised covariance matrix.
        """
        T, N = returns_matrix.shape
        if T <= N or N <= 1:
            # Fallback if sample size is smaller than variable count or univariate
            return np.cov(returns_matrix, rowvar=False)

        # 1. Compute empirical standard deviations with division-by-zero safety
        std_devs = np.std(returns_matrix, axis=0)
        std_devs = np.where(std_devs < 1e-12, 1e-12, std_devs)

        # 2. Compute empirical correlation matrix (standardized data)
        normalized_returns = (returns_matrix - np.mean(returns_matrix, axis=0)) / std_devs
        corr_matrix = np.corrcoef(normalized_returns, rowvar=False)
        
        # Handle potential NaNs in correlation matrix during dead markets
        if np.isnan(corr_matrix).any():
            return np.cov(returns_matrix, rowvar=False)

        # 3. Eigendecomposition of correlation matrix
        eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix)

        # 4. Marchenko-Pastur upper noise bound (lambda_max) for correlation matrix (sigma_sq = 1.0)
        sigma_sq = 1.0
        lambda_max = sigma_sq * ((1.0 + np.sqrt(self.q_ratio)) ** 2)

        # 5. Clip eigenvalues below noise threshold and average bulk noise variance
        cleaned_eigenvalues = eigenvalues.copy()
        noise_indices = eigenvalues < lambda_max
        if np.any(noise_indices):
            mean_noise_val = np.mean(eigenvalues[noise_indices])
            cleaned_eigenvalues[noise_indices] = mean_noise_val

        # 6. Reconstruct denoised correlation matrix
        cleaned_corr = eigenvectors @ np.diag(cleaned_eigenvalues) @ eigenvectors.T
        
        # Enforce exact unit diagonal for valid correlation structure
        d = np.sqrt(np.maximum(1e-12, np.diag(cleaned_corr)))
        cleaned_corr = cleaned_corr / np.outer(d, d)

        # 7. Convert back to covariance using original standard deviations
        denoised_cov = np.outer(std_devs, std_devs) * cleaned_corr

        return denoised_cov
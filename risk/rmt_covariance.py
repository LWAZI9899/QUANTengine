import numpy as np


class MarchenkoPasturCovarianceDenoiser:
  """Denoises empirical covariance matrices using Random Matrix Theory (RMT)

  by clipping eigenvalues below the Marchenko-Pastur theoretical noise threshold.
  """

  def __init__(self, q_ratio: float = 0.5):
    # q_ratio = N / T (number of assets N divided by sample length T)
    self.q_ratio = q_ratio

  def denoise_covariance(self, returns_matrix: np.ndarray) -> np.ndarray:
    """Takes an (T x N) returns matrix, computes empirical covariance,

    filters out pure noise eigenvalues, and reconstructs a clean covariance
    matrix.
    """
    T, N = returns_matrix.shape
    if T < N:
      # Fallback if sample size is smaller than asset count
      return np.cov(returns_matrix, rowvar=False)

    # 1. Compute empirical correlation matrix
    corr_matrix = np.corrcoef(returns_matrix, rowvar=False)
    
    # 2. Eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix)

    # 3. Marchenko-Pastur upper noise bound (lambda_max)
    sigma_sq = 1.0  # standardized variance
    lambda_max = sigma_sq * ((1.0 + np.sqrt(self.q_ratio)) ** 2)

    # 4. Clip eigenvalues below noise threshold and redistribute bulk variance
    cleaned_eigenvalues = eigenvalues.copy()
    noise_indices = eigenvalues < lambda_max
    if np.any(noise_indices):
      mean_noise_val = np.mean(eigenvalues[noise_indices])
      cleaned_eigenvalues[noise_indices] = mean_noise_val

    # 5. Reconstruct denoised correlation matrix
    cleaned_corr = eigenvectors @ np.diag(cleaned_eigenvalues) @ eigenvectors.T
    
    # Normalize diagonal back to 1.0
    d = np.sqrt(np.diag(cleaned_corr))
    cleaned_corr = cleaned_corr / np.outer(d, d)

    # 6. Convert back to covariance using standard deviations
    std_devs = np.std(returns_matrix, axis=0)
    denoised_cov = np.outer(std_devs, std_devs) * cleaned_corr

    return denoised_cov
import numpy as np

class KalmanHedgeTracker:
    def __init__(self, state_dim=2, process_variance=1e-5, measurement_variance=1e-3):
        """
        Initializes a recursive linear Kalman Filter for real-time hedge ratio tracking.
        State vector: beta_t = [beta_0, beta_1]^T (e.g., intercept and dynamic hedge ratio)
        """
        self.n = state_dim
        # Initialize state estimate (beta)
        self.beta = np.zeros(self.n)
        # Initialize error covariance matrix (P)
        self.P = np.eye(self.n) * 1.0
        # Process noise covariance (Q)
        self.Q = np.eye(self.n) * process_variance
        # Measurement noise variance (R)
        self.R = measurement_variance

    def update(self, y_t, x_t):
        """
        Updates state estimate given a new observation y_t and regressor vector x_t.
        x_t should be a 1D numpy array of shape (state_dim,), e.g., [1.0, asset_price_2].
        """
        x = np.array(x_t, dtype=float)
        
        # 1. Prediction Step (Time Update)
        # beta_{t|t-1} = beta_{t-1|t-1}
        # P_{t|t-1} = P_{t-1|t-1} + Q
        P_prior = self.P + self.Q
        
        # 2. Innovation / Measurement Residual
        # e_t = y_t - x_t^T * beta_{t|t-1}
        prediction = np.dot(x, self.beta)
        e_t = y_t - prediction
        
        # S_t = x_t^T * P_{t|t-1} * x_t + R
        S_t = np.dot(x, np.dot(P_prior, x)) + self.R
        
        # 3. Kalman Gain Calculation
        # K_t = P_{t|t-1} * x_t / S_t
        K_t = np.dot(P_prior, x) / (S_t if S_t > 0 else 1e-8)
        
        # 4. Update Step (Measurement Update)
        # beta_{t|t} = beta_{t|t-1} + K_t * e_t
        self.beta = self.beta + K_t * e_t
        
        # P_{t|t} = (I - K_t * x_t^T) * P_{t|t-1}
        identity = np.eye(self.n)
        self.P = np.dot(identity - np.outer(K_t, x), P_prior)
        
        return {
            "hedge_ratio": float(self.beta[1]),
            "intercept": float(self.beta[0]),
            "innovation": float(e_t),
            "uncertainty": float(np.trace(self.P))
        }
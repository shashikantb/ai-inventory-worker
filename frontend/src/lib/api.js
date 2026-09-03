import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("aiw_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("aiw_token");
      localStorage.removeItem("aiw_user");
      if (window.location.pathname !== "/login" && window.location.pathname !== "/signup")
        window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export const API_BASE = API;

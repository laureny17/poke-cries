import React from "react";

export const LoadingText = ({ label = "Loading" }) => (
  <>
    {label}
    <span className="loading-dots" aria-hidden="true">
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
  </>
);

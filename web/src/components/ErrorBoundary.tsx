"use client";

import React from "react";
import { Warning, ArrowCounterClockwise } from "@phosphor-icons/react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught render error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mb-4">
            <Warning size={32} weight="fill" className="text-red-500" />
          </div>
          <h2 className="text-lg font-semibold text-zinc-800 mb-2">
            Something went wrong
          </h2>
          <p className="text-sm text-zinc-500 mb-6 max-w-md">
            {this.state.error?.message || "An unexpected error occurred in this component."}
          </p>
          <button
            onClick={this.handleReset}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-100 hover:bg-zinc-200 text-sm font-medium text-zinc-700 transition-colors"
          >
            <ArrowCounterClockwise size={16} weight="fill" />
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

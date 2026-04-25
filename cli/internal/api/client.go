// Package api is a thin HTTP client for the LPS REST API.
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var httpClient = &http.Client{Timeout: 10 * time.Second}

// Client talks to one LPS API base URL.
type Client struct {
	BaseURL string
	Token   string
}

// ---- Search ----------------------------------------------------------------

type SearchHit struct {
	Distro      string `json:"distro"`
	Release     string `json:"release"`
	PackageName string `json:"package_name"`
	Version     string `json:"version"`
	Description string `json:"description"`
}

type SearchResponse struct {
	Query   string      `json:"query"`
	Results []SearchHit `json:"results"`
}

func (c *Client) Search(q, distro string) (*SearchResponse, error) {
	params := url.Values{"q": {q}}
	if distro != "" {
		params.Set("distro", distro)
	}
	var resp SearchResponse
	if err := c.get("/search?"+params.Encode(), &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// ---- Install ---------------------------------------------------------------

type InstallResponse struct {
	PackageName string `json:"package_name"`
	Distro      string `json:"distro"`
	Release     string `json:"release"`
	Command     string `json:"command"`
}

func (c *Client) Install(name, distro string) (*InstallResponse, error) {
	params := url.Values{}
	if distro != "" {
		params.Set("distro", distro)
	}
	path := "/install/" + url.PathEscape(name)
	if len(params) > 0 {
		path += "?" + params.Encode()
	}

	req, err := http.NewRequest(http.MethodGet, c.BaseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("building request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("reading response: %w", err)
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("not found")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API error %d: %s", resp.StatusCode, string(body))
	}

	// API returns plain text when Accept header is not honoured.
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "json") {
		return &InstallResponse{Command: strings.TrimSpace(string(body))}, nil
	}
	var out InstallResponse
	return &out, json.Unmarshal(body, &out)
}

// ---- Projects (info) -------------------------------------------------------

type PackageEntry struct {
	Distro      string `json:"distro"`
	Release     string `json:"release"`
	Version     string `json:"version"`
	Repo        string `json:"repo"`
	PackageName string `json:"package_name"`
}

type ProjectResponse struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	HomepageURL string         `json:"homepage_url"`
	Packages    []PackageEntry `json:"packages"`
}

func (c *Client) Project(name string) (*ProjectResponse, error) {
	var resp ProjectResponse
	if err := c.get("/projects/"+url.PathEscape(name), &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// ---- internals -------------------------------------------------------------

func (c *Client) get(path string, out any) error {
	req, err := http.NewRequest(http.MethodGet, c.BaseURL+path, nil)
	if err != nil {
		return fmt.Errorf("building request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1 MB cap
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}
	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("not found")
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("API error %d: %s", resp.StatusCode, string(body))
	}
	return json.Unmarshal(body, out)
}

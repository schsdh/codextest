package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// global token storage
var consoleToken string

// RequestRow represents minimal fields from request search API.
type RequestRow struct {
	URLID  string `json:"url_id"`
	Status int    `json:"status"`
}

// getToken retrieves authentication token from console.askurl.io.
func getToken() (string, error) {
	url := "https://console.askurl.io/api/v1/users/auth"
	payload := map[string]string{
		"platform": "nurilab",
		"authCode": "",
		"email":    "asdfasdfasdf",
		"password": "asdfasdfasdfasdf",
	}
	body, _ := json.Marshal(payload)

	req, err := http.NewRequest("POST", url, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	headers := map[string]string{
		"Connection":      "keep-alive",
		"Content-Type":    "application/json",
		"Accept":          "application/json, text/plain, */*",
		"Accept-Encoding": "identity",
		"Accept-Language": "ko-KR,ko;q=0.9",
		"User-Agent":      "Mozilla/5.0",
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	var js map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&js); err != nil {
		return "", err
	}
	token, ok := js["access_jwt"].(string)
	if !ok {
		return "", fmt.Errorf("access_jwt not found")
	}
	return token, nil
}

// buildRangeMSKSTForYesterday returns start and end milliseconds for yesterday in KST.
func buildRangeMSKSTForYesterday() (int64, int64) {
	kst := time.FixedZone("KST", 9*3600)
	now := time.Now().In(kst)
	y := now.AddDate(0, 0, -1)
	start := time.Date(y.Year(), y.Month(), y.Day(), 0, 0, 0, 0, kst)
	end := start.Add(24 * time.Hour)
	return start.UnixMilli(), end.UnixMilli()
}

// makePayload constructs payload for request search.
func makePayload(page int, start, end int64, limit int) []byte {
	prev := 0
	if page > 1 {
		prev = page - 1
	}
	data := map[string]any{
		"total": -1,
		"limit": limit,
		"prev":  prev,
		"page":  page,
		"sort":  []map[string]any{{"key": "created_at", "value": -1}},
		"filter": map[string]any{"$or": []map[string]any{
			{"created_at": map[string]any{"$gte": start, "$lt": end, "$ne": 0}},
		}},
	}
	b, _ := json.Marshal(data)
	return b
}

// requestResults fetches request results sequentially and sends status==4 rows to out channel.
func requestResults(token string, out chan<- RequestRow) error {
	start, end := buildRangeMSKSTForYesterday()
	client := &http.Client{}

	for page := 1; page <= 10; page++ {
		payload := makePayload(page, start, end, 100)
		req, err := http.NewRequest("POST", "https://console.askurl.io/api/v1/requests/search", bytes.NewReader(payload))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json, text/plain, */*")
		req.Header.Set("Accept-Encoding", "identity")
		req.Header.Set("User-Agent", "Mozilla/5.0")
		req.Header.Set("X-ACCESS-TOKEN", token)

		resp, err := client.Do(req)
		if err != nil {
			return err
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return err
		}
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("HTTP %d", resp.StatusCode)
		}
		var parsed struct {
			Rows []RequestRow `json:"rows"`
		}
		if err := json.Unmarshal(body, &parsed); err != nil {
			return err
		}
		for _, row := range parsed.Rows {
			if row.Status == 4 {
				out <- row
			}
		}
	}
	close(out)
	return nil
}

// scanResults reads rows from in channel and prints detections except scanner_id=="fixedresult".
func scanResults(token string, in <-chan RequestRow) {
	client := &http.Client{}
	var wg sync.WaitGroup

	for row := range in {
		row := row
		wg.Add(1)
		go func() {
			defer wg.Done()
			url := fmt.Sprintf("https://console.askurl.io/api/v1/scanresults/%s/summary", row.URLID)
			req, err := http.NewRequest("GET", url, nil)
			if err != nil {
				return
			}
			req.Header.Set("X-ACCESS-TOKEN", token)
			req.Header.Set("X-APIKEY", "db79c45b-1a60-4afc-9410-f2f0e2b0247a")
			req.Header.Set("Accept", "application/json, text/plain, */*")
			req.Header.Set("Accept-Encoding", "identity")
			req.Header.Set("User-Agent", "Mozilla/5.0")

			resp, err := client.Do(req)
			if err != nil {
				return
			}
			body, err := io.ReadAll(resp.Body)
			resp.Body.Close()
			if err != nil {
				return
			}
			var js map[string]any
			if err := json.Unmarshal(body, &js); err != nil {
				return
			}
			detRaw, ok := js["detections"].([]any)
			if !ok {
				return
			}
			filtered := make([]any, 0, len(detRaw))
			for _, d := range detRaw {
				m, ok := d.(map[string]any)
				if !ok {
					continue
				}
				if m["scanner_id"] != "fixedresult" {
					filtered = append(filtered, m)
				}
			}
			if len(filtered) == 0 {
				return
			}
			js["detections"] = filtered
			if b, err := json.Marshal(js); err == nil {
				fmt.Println(string(b))
			}
		}()
	}
	wg.Wait()
}

func main() {
	var err error
	consoleToken, err = getToken()
	if err != nil {
		fmt.Println("failed to get token:", err)
		return
	}

	ch := make(chan RequestRow)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		scanResults(consoleToken, ch)
	}()
	if err := requestResults(consoleToken, ch); err != nil {
		fmt.Println("request results error:", err)
	}
	wg.Wait()
}

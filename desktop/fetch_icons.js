/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

/**
 * One-off utility to probe icon availability on simpleicons.org.
 *
 * For each name in `icons`, it issues an HTTPS GET to the simple-icons CDN
 * and prints the status code plus a short prefix of the response body. Useful
 * for quickly checking which integration icons resolve before downloading
 * them into the renderer assets.
 */

const https = require('https');
const fs = require('fs');

// Integration icon names to check against the simple-icons CDN.
const icons = ['slack','microsoft','dingtalk','feishu','bluebubbles','webhook'];

// Request each icon and log its status + a snippet of the body.
for (const name of icons) {
  https.get('https://cdn.simpleicons.org/' + name, (r) => {
    let d = '';
    r.on('data', c => d += c);
    r.on('end', () => {
      console.log(name, r.statusCode, d.substring(0, 150));
    });
  }).on('error', (e) => {
    console.log(name, 'ERROR', e.message);
  });
}

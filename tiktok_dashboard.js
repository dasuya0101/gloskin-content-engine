/* Native publishing is separate from manual queue controls. No engagement actions. */
(() => {
  const el = id => document.getElementById(id);
  let postId, ticket, attemptId, loaded = false, imageUrls = [], generation = 0;
  async function api(path, body) {
    const response = await fetch('/api/tiktok/' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {'Authorization': 'Bearer ' + el('ttToken').value,
                'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store'
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'TikTok operation failed');
    return data;
  }
  function invalidate() {
    generation++;
    ticket = null; loaded = false;
    el('ttFinal').hidden = true;
    el('ttApprove').disabled = true;
    el('ttPreviewConfirmed').checked = el('ttConsent').checked = false;
    imageUrls.forEach(URL.revokeObjectURL); imageUrls = [];
    el('ttImages').replaceChildren();
  }
  function ready() {
    el('ttApprove').disabled = !(ticket && loaded && el('ttPreviewConfirmed').checked && el('ttConsent').checked);
  }
  function action(fn) {
    return async () => {
      el('ttResult').textContent = '';
      try { await fn(); } catch (err) { el('ttResult').textContent = err.message; }
    };
  }
  window.openTikTok = id => {
    postId = id; attemptId = null; invalidate();
    el('ttForm').hidden = true; el('ttIdentity').textContent = '';
    el('ttResult').textContent = 'Manual rollout is the default. Configure the owned account and checkpoints before approval.';
    el('tiktokDialog').showModal();
  };
  el('ttLoad').onclick = action(async () => {
    invalidate();
    const config = await api('config');
    const attempts = await api('attempts');
    el('ttAttempts').replaceChildren(new Option('Choose attempt', ''));
    attempts.filter(a => a.post_id === postId).forEach(a => el('ttAttempts').add(
      new Option(`${a.account_id} · ${a.stage} · ${a.scheduled_for}`, a.native_attempt_id)));
    el('ttAccount').replaceChildren(new Option('Choose account', ''));
    config.accounts.forEach(a => el('ttAccount').add(new Option(`${a.account_id} · ${a.handle} · ${a.mode}`, a.account_id)));
    el('ttResult').textContent = config.accounts.map(a => `${a.account_id}: ${a.blockers.join('; ') || 'account configured'}`).join('\n');
  });
  el('ttCreator').onclick = action(async () => {
    invalidate(); el('ttForm').hidden = true;
    const data = await api('inspect', {post_id: postId, account_id: el('ttAccount').value});
    el('ttIdentity').textContent = `${data.creator.creator_nickname} (@${data.creator.creator_username}) · Mode: ${data.mode}`;
    el('ttPrivacy').replaceChildren(new Option('Choose privacy', ''));
    data.creator.privacy_level_options.forEach(p => el('ttPrivacy').add(new Option(p, p)));
    el('ttComments').checked = el('ttMusic').checked = el('ttDraftAck').checked = false;
    el('ttComments').disabled = data.creator.comment_disabled || data.mode === 'draft';
    el('ttMusic').disabled = data.mode === 'draft';
    el('ttTitle').value = ''; el('ttCover').value = '1'; el('ttCover').max = data.photo_count;
    el('ttWhen').value = ''; el('ttCaption').textContent = data.caption;
    el('ttDisclosure').textContent = `AI-generated label: ${data.is_aigc ? 'on' : 'off'} · Commercial content: GloSkin own-brand promotion (Promotional content). Third-party paid partnership: off.`;
    el('ttDraftNotice').hidden = el('ttDraftLabel').hidden = data.mode !== 'draft';
    el('ttForm').hidden = false;
  });
  ['ttTitle','ttPrivacy','ttComments','ttMusic','ttCover','ttWhen','ttDraftAck'].forEach(id => el(id).addEventListener('input', invalidate));
  ['ttAccount','ttToken'].forEach(id => el(id).addEventListener('input', () => {invalidate(); el('ttForm').hidden = true;}));
  el('ttPreview').onclick = action(async () => {
    invalidate();
    const version = generation;
    if (!el('ttWhen').value) throw new Error('Choose a schedule time.');
    const result = await api('preview', {post_id: postId, account_id: el('ttAccount').value,
      requested_at: new Date(el('ttWhen').value).toISOString(), settings: {
        title: el('ttTitle').value, privacy_level: el('ttPrivacy').value,
        allow_comments: el('ttComments').checked, auto_add_music: el('ttMusic').checked,
        cover_index: Number(el('ttCover').value) - 1,
        draft_disclosure_acknowledged: el('ttDraftAck').checked
      }});
    if (version !== generation) return;
    ticket = result.ticket;
    const snap = result.snapshot;
    el('ttSummary').textContent = `${snap.creator.creator_nickname} · ${snap.mode} · ${snap.settings.privacy_level} · Scheduled ${new Date(snap.scheduled_for).toLocaleString()} · Preview ${result.digest.slice(0,12)}`;
    el('ttFinal').hidden = false;
    for (let i = 0; i < snap.photos.length; i++) {
      const response = await fetch(`/api/tiktok/preview/${encodeURIComponent(ticket)}/${i}`, {
        headers: {'Authorization': 'Bearer ' + el('ttToken').value}, cache: 'no-store'});
      if (!response.ok) throw new Error('Preview image could not be loaded. Render again.');
      const blob = await response.blob();
      if (version !== generation) return;
      const url = URL.createObjectURL(blob); imageUrls.push(url);
      const img = new Image(); img.src = url; img.alt = `Photo ${i+1}${i === snap.settings.cover_index ? ' (cover)' : ''}`;
      img.style.width = '270px'; img.style.height = 'auto';
      await img.decode();
      if (version !== generation) return;
      el('ttImages').appendChild(img);
    }
    loaded = true; ready();
  });
  el('ttPreviewConfirmed').onchange = el('ttConsent').onchange = ready;
  el('ttAttempts').onchange = () => {attemptId = el('ttAttempts').value;};
  el('ttCancel').onclick = action(async () => {
    if (!attemptId) throw new Error('Select an unsubmitted attempt.');
    await api('cancel-schedule', {attempt_id: attemptId});
    invalidate();
    el('ttResult').textContent = 'Local schedule cancelled. Edit the settings and render a fresh preview to approve again.';
  });
  el('ttApprove').onclick = action(async () => {
    if (el('ttApprove').disabled) return;
    el('ttApprove').disabled = true;
    const record = await api('approve', {ticket, content_preview_confirmed: el('ttPreviewConfirmed').checked,
                                       express_consent: el('ttConsent').checked});
    attemptId = record.native_attempt_id;
    invalidate();
    el('ttResult').textContent = `Approval recorded and queued for ${record.scheduled_for}. Attempt: ${attemptId}. An enabled worker is required to submit.`;
  });
  el('ttConnect').onclick = action(async () => {
    const result = await api('oauth/start', {account_id: el('ttAccount').value});
    window.location.assign(result.authorization_url);
  });
  el('ttRefresh').onclick = action(async () => {
    if (!attemptId) throw new Error('Approve a post first, or use tiktok-refresh with its saved attempt ID.');
    const record = await api('refresh', {attempt_id: attemptId});
    el('ttResult').textContent = `${record.status} · ${record.tiktok_status || ''} · ${record.url || record.error || 'No public URL available'}`;
  });
  el('tiktokDialog').addEventListener('close', invalidate);
})();

;;; update-readme.el --- Sync the org file lists in README.md  -*- lexical-binding: t; -*-

;; Usage:
;;   1. (load-file "~/path/to/Org/tools/update-readme.el") in your init file
;;   2. M-x update-readme         -- update the lists, refresh an open README buffer
;;   3. M-x update-readme-check   -- check only, do not write
;;
;; All the work is done by tools/update-readme.py; this file is a thin wrapper.

(defgroup update-readme nil
  "Keep the org file lists in README.md in sync."
  :group 'org)

(defcustom update-readme-python "python"
  "Python executable used to run the script."
  :type 'string)

(defcustom update-readme-script "tools/update-readme.py"
  "Script path, relative to the repository root."
  :type 'string)

(defun update-readme--root ()
  "Return the repository root, or nil when it cannot be found."
  (when-let* ((buf (or (buffer-file-name) default-directory))
              (root (locate-dominating-file buf update-readme-script)))
    (file-name-as-directory (expand-file-name root))))

(defun update-readme--run (&rest args)
  "Run the script with ARGS.  Return (EXIT-CODE . OUTPUT)."
  (let ((root (or (update-readme--root)
                  (user-error "Repository root not found (no %s)" update-readme-script)))
        (default-directory (update-readme--root)))
    (with-temp-buffer
      (let* ((coding-system-for-read 'utf-8-unix)
             (coding-system-for-write 'utf-8-unix)
             (code (apply #'call-process update-readme-python nil t nil
                          (expand-file-name update-readme-script root) args))
             (output (string-trim (buffer-string))))
        (cons code output)))))

(defun update-readme--refresh-buffer ()
  "Revert the README.md buffer when it is open and unmodified."
  (when-let* ((root (ignore-errors (update-readme--root)))
              (path (expand-file-name "README.md" root))
              (buf (find-buffer-visiting path)))
    (with-current-buffer buf
      (unless (buffer-modified-p)
        (revert-buffer t t t)))))

(defun update-readme--report (result)
  "Report RESULT, signalling an error when the script failed."
  (let ((code (car result))
        (output (cdr result)))
    (update-readme--refresh-buffer)
    (if (zerop code)
        (message "%s" (if (string-empty-p output) "README.md is up to date" output))
      (user-error "update-readme failed (exit %s):\n%s" code output))))

;;;###autoload
(defun update-readme ()
  "Regenerate the org file lists in README.md, grouped by directory."
  (interactive)
  (update-readme--report (update-readme--run)))

;;;###autoload
(defun update-readme-check ()
  "Check whether the lists in README.md match the org files on disk."
  (interactive)
  (let ((result (update-readme--run "--check")))
    (if (zerop (car result))
        (message "README.md is up to date")
      (user-error "README.md is out of sync: %s" (cdr result)))))

(provide 'update-readme)
;;; update-readme.el ends here

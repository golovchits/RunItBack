import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

type BaseProps = {
  label?: string;
  hint?: string;
  error?: string;
  mono?: boolean;
  leadingIcon?: React.ReactNode;
};

type InputProps = BaseProps & InputHTMLAttributes<HTMLInputElement> & {
  as?: "input";
};

type TextareaProps = BaseProps & TextareaHTMLAttributes<HTMLTextAreaElement> & {
  as: "textarea";
};

type Props = InputProps | TextareaProps;

export function InputField(props: Props) {
  const { label, hint, error, mono, leadingIcon, ...rest } = props;
  const commonClass = `w-full bg-transparent focus:outline-none ${
    mono ? "font-mono" : "font-ui"
  }`;
  const style = {
    color: "var(--rib-text0)",
    fontSize: mono ? 13 : 13.5,
    lineHeight: mono ? "20px" : "22px",
  } as const;
  const showLabel = label != null;
  return (
    <label className="block">
      {showLabel && (
        <div
          className="mb-[6px] text-[11px] font-semibold uppercase"
          style={{
            color: "var(--rib-text2)",
            letterSpacing: "0.1em",
          }}
        >
          {label}
        </div>
      )}
      <div
        className="flex items-center gap-[10px] px-[12px] py-[9px]"
        style={{
          background: "var(--rib-bg1)",
          border: `1px solid ${error ? "var(--rib-critical)" : "var(--rib-line)"}`,
          borderRadius: 6,
          transition: "border-color 0.15s",
        }}
      >
        {leadingIcon && (
          <div style={{ color: "var(--rib-text3)", flexShrink: 0 }}>
            {leadingIcon}
          </div>
        )}
        {rest.as === "textarea" ? (
          <textarea
            {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
            className={commonClass}
            style={{ ...style, resize: "vertical", minHeight: 100 }}
          />
        ) : (
          <input
            {...(rest as InputHTMLAttributes<HTMLInputElement>)}
            className={commonClass}
            style={style}
          />
        )}
      </div>
      {(hint || error) && (
        <div
          className="mt-[6px] text-[12px]"
          style={{ color: error ? "var(--rib-critical)" : "var(--rib-text2)" }}
        >
          {error ?? hint}
        </div>
      )}
    </label>
  );
}

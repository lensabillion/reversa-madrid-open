// Next.js runs PostCSS on every stylesheet. Tailwind CSS v4 is this plugin and needs no
// tailwind.config file: it finds the class names in the source files itself.
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
